from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.face_pipeline import FacePipeline


class RecognitionPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedThresholds:
    minimum_similarity: float
    minimum_margin: float
    validation_id: str


def validation_manifest_signature(manifest: dict[str, Any], key: bytes) -> str:
    signed_content = dict(manifest)
    approval = dict(signed_content.get("approval", {}))
    approval.pop("signature", None)
    signed_content["approval"] = approval
    canonical = json.dumps(signed_content, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def load_validated_thresholds(pipeline: FacePipeline) -> ValidatedThresholds | None:
    configured = os.getenv("VERITY_RECOGNITION_VALIDATION_MANIFEST")
    if not configured:
        return None
    path = Path(configured).expanduser()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest root must be an object.")
        if manifest.get("approved_for_automatic_attendance") is not True:
            return None
        if manifest.get("detector_sha256") != pipeline.detector_sha256:
            raise ValueError("Validation manifest detector hash does not match the active model.")
        if manifest.get("embedder_sha256") != pipeline.embedder_sha256:
            raise ValueError("Validation manifest embedder hash does not match the active model.")
        minimum_similarity = float(manifest["minimum_similarity"])
        minimum_margin = float(manifest["minimum_margin"])
        validation_id = manifest["validation_id"]
        approval = manifest["approval"]
        threshold_curve = manifest["threshold_curve"]
        if not isinstance(threshold_curve, list) or any(
            not isinstance(item, dict) for item in threshold_curve
        ):
            raise ValueError("Validation threshold curve must be a list of metric objects.")
        selected_metrics = [
            item
            for item in threshold_curve
            if item.get("minimum_similarity") == minimum_similarity
            and item.get("minimum_margin") == minimum_margin
        ]
        if (
            not 0.0 <= minimum_similarity <= 1.0
            or not 0.0 <= minimum_margin <= 2.0
            or not isinstance(validation_id, str)
            or not validation_id.strip()
            or not isinstance(manifest.get("dataset_sha256"), str)
            or len(manifest["dataset_sha256"]) != 64
            or not isinstance(manifest.get("dataset_images"), int)
            or manifest["dataset_images"] < 30
            or not isinstance(manifest.get("evaluation_images"), int)
            or manifest["evaluation_images"] < 30
            or not isinstance(manifest.get("enrollment_identities"), int)
            or manifest["enrollment_identities"] < 30
            or not {"low", "medium", "high"}.issubset(
                {str(value).lower() for value in manifest.get("lighting_buckets", [])}
            )
            or not isinstance(approval, dict)
            or approval.get("approved") is not True
            or not isinstance(approval.get("approved_by"), str)
            or not approval["approved_by"].strip()
            or not isinstance(approval.get("approved_at"), str)
            or not isinstance(approval.get("approval_reference"), str)
            or not approval["approval_reference"].strip()
            or not isinstance(approval.get("approval_key_id"), str)
            or not isinstance(approval.get("signature"), str)
            or len(selected_metrics) != 1
            or not math.isfinite(float(selected_metrics[0].get("false_accept_rate", float("nan"))))
            or not math.isfinite(float(selected_metrics[0].get("false_reject_rate", float("nan"))))
        ):
            raise ValueError("Validation report, selected metrics, or institutional approval is incomplete.")
        approved_at = datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00"))
        if approved_at.tzinfo is None or approved_at.utcoffset() is None:
            raise ValueError("Approval timestamp must include a timezone.")
        int(manifest["dataset_sha256"], 16)
        approval_key_id = os.getenv("VERITY_RECOGNITION_APPROVAL_KEY_ID", "")
        encoded_key = os.getenv("VERITY_RECOGNITION_APPROVAL_KEY", "")
        if not approval_key_id or not encoded_key:
            raise ValueError("Institutional approval verification key is not configured.")
        if approval["approval_key_id"] != approval_key_id:
            raise ValueError("Approval key ID does not match the active verification key.")
        approval_key = base64.b64decode(encoded_key.encode("ascii"), validate=True)
        if len(approval_key) != 32:
            raise ValueError("Approval verification key must be 32 bytes.")
        expected_signature = validation_manifest_signature(manifest, approval_key)
        if not hmac.compare_digest(approval["signature"], expected_signature):
            raise ValueError("Validation manifest approval signature is invalid.")
        if not 0.0 <= selected_metrics[0]["false_accept_rate"] <= 1.0 or not 0.0 <= selected_metrics[0]["false_reject_rate"] <= 1.0:
            raise ValueError("Validation report contains out-of-range error rates.")
    except FileNotFoundError as error:
        raise RecognitionPolicyError("The configured validation manifest does not exist.") from error
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RecognitionPolicyError("The recognition validation manifest is invalid.") from error
    return ValidatedThresholds(minimum_similarity, minimum_margin, validation_id)


def automatic_attendance_enabled() -> bool:
    return os.getenv("VERITY_AUTO_ATTENDANCE_ENABLED", "").strip().lower() == "true"
