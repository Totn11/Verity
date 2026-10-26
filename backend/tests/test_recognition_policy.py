from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.face_pipeline import FacePipeline
from app.services.recognition_policy import (
    RecognitionPolicyError,
    automatic_attendance_enabled,
    load_validated_thresholds,
    validation_manifest_signature,
)


class RecognitionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.detector = root / "detector.onnx"
        self.embedder = root / "embedder.onnx"
        self.detector.write_bytes(b"detector")
        self.embedder.write_bytes(b"embedder")
        self.pipeline = FacePipeline(self.detector, self.embedder)
        self.manifest = root / "validation.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_absent_or_unapproved_manifest_never_enables_thresholds(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(load_validated_thresholds(self.pipeline))
        self.manifest.write_text(
            json.dumps({"approved_for_automatic_attendance": False}), encoding="utf-8"
        )
        with patch.dict(
            "os.environ",
            {"VERITY_RECOGNITION_VALIDATION_MANIFEST": str(self.manifest)},
        ):
            self.assertIsNone(load_validated_thresholds(self.pipeline))
            self.assertFalse(automatic_attendance_enabled())

    def test_approved_thresholds_require_dataset_coverage_and_model_hashes(self) -> None:
        report = {
            "approved_for_automatic_attendance": True,
            "approval": {
                "approved": True,
                "approved_by": "institutional-review",
                "approved_at": "2026-10-26T12:00:00+00:00",
                "approval_reference": "IRB-123",
                "approval_key_id": "test-approval-key",
            },
            "validation_id": "validation-1",
            "dataset_sha256": "a" * 64,
            "dataset_images": 300,
            "evaluation_images": 100,
            "enrollment_identities": 30,
            "lighting_buckets": ["low", "medium", "high"],
            "detector_sha256": self.pipeline.detector_sha256,
            "embedder_sha256": self.pipeline.embedder_sha256,
            "minimum_similarity": 0.75,
            "minimum_margin": 0.1,
            "threshold_curve": [
                {
                    "minimum_similarity": 0.75,
                    "minimum_margin": 0.1,
                    "false_accept_rate": 0.01,
                    "false_reject_rate": 0.05,
                }
            ],
        }
        signing_key = bytes(range(32))
        report["approval"]["signature"] = validation_manifest_signature(report, signing_key)
        self.manifest.write_text(json.dumps(report), encoding="utf-8")
        with patch.dict(
            "os.environ",
            {
                "VERITY_RECOGNITION_VALIDATION_MANIFEST": str(self.manifest),
                "VERITY_AUTO_ATTENDANCE_ENABLED": "true",
                "VERITY_RECOGNITION_APPROVAL_KEY_ID": "test-approval-key",
                "VERITY_RECOGNITION_APPROVAL_KEY": base64.b64encode(signing_key).decode(),
            },
        ):
            thresholds = load_validated_thresholds(self.pipeline)
            self.assertIsNotNone(thresholds)
            self.assertEqual(thresholds.minimum_similarity, 0.75)
            self.assertTrue(automatic_attendance_enabled())

        report["embedder_sha256"] = "b" * 64
        self.manifest.write_text(json.dumps(report), encoding="utf-8")
        with patch.dict(
            "os.environ",
            {"VERITY_RECOGNITION_VALIDATION_MANIFEST": str(self.manifest)},
        ):
            with self.assertRaises(RecognitionPolicyError):
                load_validated_thresholds(self.pipeline)

    def test_threshold_report_without_representative_coverage_is_rejected(self) -> None:
        report = {
            "approved_for_automatic_attendance": True,
            "approval": {
                "approved": True,
                "approved_by": "reviewer",
                "approved_at": "2026-10-26T12:00:00+00:00",
                "approval_reference": "review-1",
                "approval_key_id": "test-approval-key",
            },
            "validation_id": "validation-1",
            "dataset_sha256": "a" * 64,
            "dataset_images": 10,
            "evaluation_images": 8,
            "enrollment_identities": 3,
            "lighting_buckets": ["low"],
            "detector_sha256": self.pipeline.detector_sha256,
            "embedder_sha256": self.pipeline.embedder_sha256,
            "minimum_similarity": 0.7,
            "minimum_margin": 0.1,
            "threshold_curve": [
                {
                    "minimum_similarity": 0.7,
                    "minimum_margin": 0.1,
                    "false_accept_rate": 0.0,
                    "false_reject_rate": 0.0,
                }
            ],
        }
        signing_key = bytes(range(32))
        report["approval"]["signature"] = validation_manifest_signature(report, signing_key)
        self.manifest.write_text(json.dumps(report), encoding="utf-8")
        with patch.dict(
            "os.environ",
            {
                "VERITY_RECOGNITION_VALIDATION_MANIFEST": str(self.manifest),
                "VERITY_RECOGNITION_APPROVAL_KEY_ID": "test-approval-key",
                "VERITY_RECOGNITION_APPROVAL_KEY": base64.b64encode(signing_key).decode(),
            },
        ):
            with self.assertRaises(RecognitionPolicyError):
                load_validated_thresholds(self.pipeline)
