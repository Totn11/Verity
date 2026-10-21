from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from jwt import InvalidTokenError

from app.db.models import User, UserRole

TOKEN_ISSUER = "verity-api"
TOKEN_TTL = timedelta(hours=8)
TOKEN_LEEWAY_SECONDS = 30
REQUIRED_CLAIMS = (
    "exp",
    "iat",
    "nbf",
    "iss",
    "aud",
    "sub",
    "sid",
    "jti",
    "ver",
    "role",
)


class TokenConfigurationError(RuntimeError):
    """Raised when required JWT signing or verification configuration is invalid."""


@dataclass(frozen=True)
class TokenKeySet:
    signing_kid: str
    private_key: Ed25519PrivateKey
    public_keys: dict[str, Ed25519PublicKey]
    audience: str


def _decode_pem(value: str) -> bytes:
    return value.replace("\\n", "\n").encode("utf-8")


def _require_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise TokenConfigurationError(
            "VERITY_JWT_AUDIENCE must be an application origin such as https://app.example."
        )
    return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache(maxsize=1)
def get_token_keyset() -> TokenKeySet:
    signing_kid = os.getenv("VERITY_JWT_SIGNING_KID", "").strip()
    private_pem = os.getenv("VERITY_JWT_PRIVATE_KEY", "").strip()
    public_keys_json = os.getenv("VERITY_JWT_PUBLIC_KEYS", "").strip()
    audience = os.getenv("VERITY_JWT_AUDIENCE", "").strip()
    if not all((signing_kid, private_pem, public_keys_json, audience)):
        raise TokenConfigurationError(
            "Set VERITY_JWT_SIGNING_KID, VERITY_JWT_PRIVATE_KEY, "
            "VERITY_JWT_PUBLIC_KEYS, and VERITY_JWT_AUDIENCE."
        )

    try:
        private_key = serialization.load_pem_private_key(
            _decode_pem(private_pem), password=None
        )
        raw_public_keys: Any = json.loads(public_keys_json)
        if not isinstance(raw_public_keys, dict) or not raw_public_keys:
            raise ValueError("public keys must be a non-empty JSON object")
        public_keys = {
            kid: serialization.load_pem_public_key(_decode_pem(pem))
            for kid, pem in raw_public_keys.items()
            if isinstance(kid, str) and kid and isinstance(pem, str)
        }
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise TokenConfigurationError("JWT signing keys are invalid.") from error

    if not isinstance(private_key, Ed25519PrivateKey) or any(
        not isinstance(key, Ed25519PublicKey) for key in public_keys.values()
    ):
        raise TokenConfigurationError("JWT keys must use Ed25519.")
    active_public_key = public_keys.get(signing_kid)
    if active_public_key is None:
        raise TokenConfigurationError(
            "VERITY_JWT_PUBLIC_KEYS must include the active signing key ID."
        )
    private_public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    active_public_bytes = active_public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    if private_public_bytes != active_public_bytes:
        raise TokenConfigurationError("Active JWT signing and verification keys do not match.")

    return TokenKeySet(
        signing_kid=signing_kid,
        private_key=private_key,
        public_keys=public_keys,
        audience=_require_origin(audience),
    )


def issue_claims(
    user: User,
    session_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> dict[str, str | int]:
    issued_at = now or datetime.now(UTC)
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise ValueError("Token issue time must be timezone-aware.")
    issued_epoch = int(issued_at.timestamp())
    return {
        "iss": TOKEN_ISSUER,
        "aud": get_token_keyset().audience,
        "sub": str(user.id),
        "sid": str(session_id),
        "jti": str(uuid.uuid4()),
        "iat": issued_epoch,
        "nbf": issued_epoch,
        "exp": int((issued_at + TOKEN_TTL).timestamp()),
        "role": getattr(user.role, "value", user.role),
        "ver": user.session_version or 0,
    }


def encode_token(claims: dict[str, str | int]) -> str:
    keyset = get_token_keyset()
    return jwt.encode(
        claims,
        keyset.private_key,
        algorithm="EdDSA",
        headers={"kid": keyset.signing_kid, "typ": "JWT"},
    )


def verify_token(token: str) -> dict[str, Any]:
    keyset = get_token_keyset()
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "EdDSA" or not isinstance(kid, str):
            raise InvalidTokenError("Unsupported token header.")
        public_key = keyset.public_keys.get(kid)
        if public_key is None:
            raise InvalidTokenError("Unknown signing key.")
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["EdDSA"],
            audience=keyset.audience,
            issuer=TOKEN_ISSUER,
            leeway=TOKEN_LEEWAY_SECONDS,
            options={"require": list(REQUIRED_CLAIMS)},
        )
        uuid.UUID(claims["sub"])
        uuid.UUID(claims["sid"])
        uuid.UUID(claims["jti"])
        if (
            claims["role"] not in {role.value for role in UserRole}
            or isinstance(claims["ver"], bool)
            or not isinstance(claims["ver"], int)
            or claims["ver"] < 0
        ):
            raise InvalidTokenError("Invalid identity claims.")
        return claims
    except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise InvalidTokenError("Invalid session token.") from error
