from __future__ import annotations

import argparse
import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.services.recognition_policy import validation_manifest_signature


def _load_signing_key() -> tuple[str, bytes]:
    key_id = os.getenv("VERITY_RECOGNITION_APPROVAL_KEY_ID", "").strip()
    encoded_key = os.getenv("VERITY_RECOGNITION_APPROVAL_KEY", "")
    if not key_id or not encoded_key:
        raise RuntimeError(
            "Institutional approval signing key ID and 32-byte base64 key are required."
        )
    try:
        key = base64.b64decode(encoded_key.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise RuntimeError("Approval signing key must be valid base64.") from error
    if len(key) != 32:
        raise RuntimeError("Approval signing key must decode to exactly 32 bytes.")
    return key_id, key


def _validate_report(report: dict, similarity: float, margin: float) -> None:
    if report.get("approved_for_automatic_attendance") is True:
        raise ValueError("This validation manifest has already been approved.")
    curve = report.get("threshold_curve")
    if not isinstance(curve, list):
        raise ValueError("The validation report has no threshold curve.")
    choices = [
        item
        for item in curve
        if isinstance(item, dict)
        and item.get("minimum_similarity") == similarity
        and item.get("minimum_margin") == margin
    ]
    if len(choices) != 1:
        raise ValueError("Choose exactly one threshold pair present in the report.")
    metrics = choices[0]
    if metrics.get("false_accept_rate") is None or metrics.get("false_reject_rate") is None:
        raise ValueError("The selected threshold pair has no measurable FAR and FRR.")
    if (
        report.get("dataset_images", 0) < 30
        or report.get("evaluation_images", 0) < 30
        or report.get("enrollment_identities", 0) < 30
        or not {"low", "medium", "high"}.issubset(
            {str(value).lower() for value in report.get("lighting_buckets", [])}
        )
    ):
        raise ValueError("The report does not meet minimum identity, evaluation, and lighting coverage.")
    if not all(
        isinstance(report.get(field), str) and len(report[field]) == 64
        for field in ("dataset_sha256", "detector_sha256", "embedder_sha256")
    ):
        raise ValueError("Dataset and model SHA-256 values are required.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sign an institution-reviewed, locally generated recognition validation report."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--minimum-similarity", required=True, type=float)
    parser.add_argument("--minimum-margin", required=True, type=float)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-reference", required=True)
    arguments = parser.parse_args()
    if not 0.0 <= arguments.minimum_similarity <= 1.0:
        parser.error("Minimum similarity must be between 0 and 1.")
    if not 0.0 <= arguments.minimum_margin <= 2.0:
        parser.error("Minimum margin must be between 0 and 2.")
    if not arguments.approved_by.strip() or not arguments.approval_reference.strip():
        parser.error("Approver and institutional approval reference cannot be empty.")

    report = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Validation report root must be a JSON object.")
    _validate_report(report, arguments.minimum_similarity, arguments.minimum_margin)
    key_id, key = _load_signing_key()
    report["minimum_similarity"] = arguments.minimum_similarity
    report["minimum_margin"] = arguments.minimum_margin
    report["approved_for_automatic_attendance"] = True
    report["approval"] = {
        "approved": True,
        "approved_by": arguments.approved_by.strip(),
        "approved_at": datetime.now(UTC).isoformat(),
        "approval_reference": arguments.approval_reference.strip(),
        "approval_key_id": key_id,
    }
    report["approval"]["signature"] = validation_manifest_signature(report, key)
    temporary = arguments.manifest.with_name(f".{arguments.manifest.name}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, arguments.manifest)
    print(f"Signed institutional validation approval for {report['validation_id']}.")


if __name__ == "__main__":
    main()
