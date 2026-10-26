from __future__ import annotations

import base64
import json
import os
import struct
import uuid
from dataclasses import dataclass

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.face_pipeline import EXPECTED_EMBEDDING_SIZE

_ENVELOPE_VERSION = 1
_NONCE_SIZE = 12


class BiometricKeyConfigurationError(RuntimeError):
    pass


class EncryptedTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class EncryptedValue:
    ciphertext: bytes
    key_id: str


class TemplateCipher:
    """AES-256-GCM template envelope encryption with externally managed keys."""

    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        if active_key_id not in keys:
            raise BiometricKeyConfigurationError("The active biometric key ID is not configured.")
        if not keys or any(len(key) != 32 for key in keys.values()):
            raise BiometricKeyConfigurationError("Each biometric encryption key must be 32 bytes.")
        self._keys = dict(keys)
        self._active_key_id = active_key_id

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    @classmethod
    def from_environment(cls) -> TemplateCipher:
        raw_keys = os.getenv("VERITY_TEMPLATE_KEYS")
        active_key_id = os.getenv("VERITY_TEMPLATE_ACTIVE_KEY_ID")
        if not raw_keys or not active_key_id:
            raise BiometricKeyConfigurationError(
                "Biometric templates are disabled until externally managed encryption keys are configured."
            )
        try:
            encoded_keys = json.loads(raw_keys)
            if not isinstance(encoded_keys, dict) or not all(
                isinstance(key_id, str) and isinstance(value, str)
                for key_id, value in encoded_keys.items()
            ):
                raise ValueError("Expected a JSON object of key IDs and base64 keys.")
            keys = {
                key_id: base64.urlsafe_b64decode(value.encode("ascii"))
                for key_id, value in encoded_keys.items()
            }
            return cls(keys, active_key_id)
        except (ValueError, UnicodeEncodeError, json.JSONDecodeError) as error:
            raise BiometricKeyConfigurationError(
                "VERITY_TEMPLATE_KEYS must be a JSON map of key IDs to base64-encoded 32-byte keys."
            ) from error

    def encrypt(
        self, embedding: np.ndarray, student_id: uuid.UUID, model_version: str
    ) -> EncryptedValue:
        vector = np.asarray(embedding, dtype="<f4").reshape(-1)
        if (
            vector.shape != (EXPECTED_EMBEDDING_SIZE,)
            or not np.all(np.isfinite(vector))
            or np.linalg.norm(vector) <= 1e-12
        ):
            raise ValueError("Only a finite, non-zero SFace embedding can be encrypted.")
        vector = vector / np.linalg.norm(vector)
        plaintext = struct.pack("!I", vector.size) + vector.tobytes()
        key_id = self._active_key_id
        nonce = os.urandom(_NONCE_SIZE)
        aad = _associated_data(student_id, model_version)
        ciphertext = bytes((_ENVELOPE_VERSION,)) + nonce + AESGCM(self._keys[key_id]).encrypt(
            nonce, plaintext, aad
        )
        return EncryptedValue(ciphertext, key_id)

    def decrypt(
        self,
        encrypted: bytes,
        key_id: str,
        student_id: uuid.UUID,
        model_version: str,
    ) -> np.ndarray:
        if key_id not in self._keys:
            raise BiometricKeyConfigurationError(f"Biometric decryption key {key_id!r} is unavailable.")
        if len(encrypted) < 1 + _NONCE_SIZE + 16 or encrypted[0] != _ENVELOPE_VERSION:
            raise EncryptedTemplateError("Encrypted template envelope is invalid.")
        nonce = encrypted[1 : 1 + _NONCE_SIZE]
        aad = _associated_data(student_id, model_version)
        try:
            plaintext = AESGCM(self._keys[key_id]).decrypt(
                nonce, encrypted[1 + _NONCE_SIZE :], aad
            )
        except InvalidTag as error:
            raise EncryptedTemplateError(
                "Template authentication failed; the record or its associated metadata was changed."
            ) from error
        if len(plaintext) < 4:
            raise EncryptedTemplateError("Encrypted template payload is truncated.")
        (vector_size,) = struct.unpack("!I", plaintext[:4])
        if vector_size != EXPECTED_EMBEDDING_SIZE or len(plaintext) != 4 + vector_size * 4:
            raise EncryptedTemplateError("Encrypted template has an unsupported vector format.")
        vector = np.frombuffer(plaintext[4:], dtype="<f4").astype(np.float32, copy=True)
        norm = float(np.linalg.norm(vector))
        if not np.all(np.isfinite(vector)) or norm <= 1e-12:
            raise EncryptedTemplateError("Encrypted template contains an invalid vector.")
        return vector / norm


def configured_retention_days() -> int:
    raw_days = os.getenv("VERITY_FACE_TEMPLATE_RETENTION_DAYS")
    if raw_days is None:
        raise BiometricKeyConfigurationError(
            "Set VERITY_FACE_TEMPLATE_RETENTION_DAYS before enabling biometric enrollment."
        )
    try:
        days = int(raw_days)
    except ValueError as error:
        raise BiometricKeyConfigurationError(
            "VERITY_FACE_TEMPLATE_RETENTION_DAYS must be a positive integer."
        ) from error
    if days < 1 or days > 3650:
        raise BiometricKeyConfigurationError(
            "VERITY_FACE_TEMPLATE_RETENTION_DAYS must be between 1 and 3650."
        )
    return days


def _associated_data(student_id: uuid.UUID, model_version: str) -> bytes:
    return f"verity-face-template:v{_ENVELOPE_VERSION}:{student_id}:{model_version}".encode()
