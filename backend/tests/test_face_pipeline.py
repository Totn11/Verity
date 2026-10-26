from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

import numpy as np
from fastapi import HTTPException

from app.services.biometric_crypto import (
    BiometricKeyConfigurationError,
    EncryptedTemplateError,
    TemplateCipher,
    configured_retention_days,
)
from app.services.face_pipeline import (
    FacePipeline,
    LowQualityFaceError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    QualityPolicy,
    assess_quality,
    match_embedding,
)


def _face(x: int = 30, y: int = 30, width: int = 120, height: int = 120) -> np.ndarray:
    return np.asarray([x, y, width, height, *([50.0] * 10), 0.99], dtype=np.float32)


class FacePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.detector_path = Path(self.directory.name) / "yunet.onnx"
        self.embedder_path = Path(self.directory.name) / "sface.onnx"
        self.detector_path.write_bytes(b"yunet-test-artifact")
        self.embedder_path.write_bytes(b"sface-test-artifact")
        self.pipeline = FacePipeline(self.detector_path, self.embedder_path)
        self.pipeline.decode_image = Mock(
            return_value=np.random.default_rng(17).integers(50, 210, (220, 220, 3), dtype=np.uint8)
        )
        self.pipeline.detector.detect = Mock(return_value=())
        self.pipeline.embedder.extract = Mock(return_value=np.ones(128, dtype=np.float32))

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_detector_returns_no_face_and_multiple_face_failures(self) -> None:
        with self.assertRaises(NoFaceDetectedError):
            self.pipeline.infer(b"image")
        self.pipeline.detector.detect.return_value = (_face(), _face(60, 60))
        with self.assertRaises(MultipleFacesDetectedError):
            self.pipeline.infer(b"image")

    def test_low_quality_is_rejected_before_embedding(self) -> None:
        self.pipeline.decode_image.return_value = np.zeros((220, 220, 3), dtype=np.uint8)
        self.pipeline.detector.detect.return_value = (_face(),)
        with self.assertRaises(LowQualityFaceError) as caught:
            self.pipeline.infer(b"image")
        self.assertIn("low_brightness", caught.exception.metrics.warnings)
        self.pipeline.embedder.extract.assert_not_called()

    def test_quality_assesses_the_face_region_and_detects_small_faces(self) -> None:
        image = np.random.default_rng(3).integers(40, 200, (200, 200, 3), dtype=np.uint8)
        quality = assess_quality(
            image,
            20,
            20,
            60,
            60,
            QualityPolicy(minimum_face_dimension=80),
        )
        self.assertIn("face_too_small", quality.warnings)

    def test_embedding_output_is_normalized(self) -> None:
        self.pipeline.detector.detect.return_value = (_face(),)
        self.pipeline.embedder.extract.return_value = np.arange(1, 129, dtype=np.float32)
        observation = self.pipeline.infer(b"image")
        self.assertEqual(observation.embedding.shape, (128,))
        self.assertAlmostEqual(float(np.linalg.norm(observation.embedding)), 1.0, places=6)
        self.assertEqual(observation.detector_sha256, self.pipeline.detector_sha256)

    def test_image_input_is_size_bounded_and_corruption_rejected(self) -> None:
        from app.services.face_pipeline import InvalidFaceImageError

        with self.assertRaisesRegex(InvalidFaceImageError, "5 MiB"):
            FacePipeline.decode_image(b"x" * (5 * 1024 * 1024 + 1))
        with self.assertRaises(InvalidFaceImageError):
            FacePipeline.decode_image(b"not-an-image")


class MatchingTests(unittest.TestCase):
    def test_matches_high_similarity_and_rejects_below_threshold(self) -> None:
        probe = np.zeros(128, dtype=np.float32)
        probe[0] = 1
        result = match_embedding(
            probe,
            {"student-a": probe.copy(), "student-b": np.eye(1, 128, 1, dtype=np.float32).reshape(-1)},
            0.8,
            0.2,
        )
        self.assertEqual((result.outcome, result.student_id), ("matched", "student-a"))
        rejected = match_embedding(probe, {"student-a": -probe}, 0.8, 0.2)
        self.assertEqual(rejected.outcome, "uncertain")
        self.assertIsNone(rejected.student_id)

    def test_ambiguous_and_unvalidated_candidates_are_deferred(self) -> None:
        probe = np.zeros(128, dtype=np.float32)
        probe[0] = 1
        close = probe.copy()
        close[1] = 0.1
        ambiguous = match_embedding(probe, {"student-a": probe, "student-b": close}, 0.5, 0.2)
        self.assertEqual(ambiguous.outcome, "uncertain")
        self.assertIsNone(ambiguous.student_id)
        unvalidated = match_embedding(probe, {"student-a": probe}, None, None)
        self.assertEqual(unvalidated.outcome, "uncertain")
        self.assertIsNone(unvalidated.student_id)


class TemplateEncryptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key_id = "test-key-1"
        self.student_id = uuid.uuid4()
        self.model_version = "sface:test"
        self.cipher = TemplateCipher({self.key_id: bytes(range(32))}, self.key_id)

    def test_encryption_roundtrip_is_normalized_and_authenticated(self) -> None:
        vector = np.arange(1, 129, dtype=np.float32)
        encrypted = self.cipher.encrypt(vector, self.student_id, self.model_version)
        restored = self.cipher.decrypt(
            encrypted.ciphertext, encrypted.key_id, self.student_id, self.model_version
        )
        self.assertTrue(np.allclose(restored, vector / np.linalg.norm(vector)))
        self.assertNotIn(vector.tobytes(), encrypted.ciphertext)
        with self.assertRaises(EncryptedTemplateError):
            self.cipher.decrypt(
                encrypted.ciphertext, encrypted.key_id, uuid.uuid4(), self.model_version
            )

    def test_unknown_key_and_malformed_vectors_fail_closed(self) -> None:
        with self.assertRaises(BiometricKeyConfigurationError):
            self.cipher.decrypt(b"bad", "missing", self.student_id, self.model_version)
        with self.assertRaises(ValueError):
            self.cipher.encrypt(np.zeros(128), self.student_id, self.model_version)
        with self.assertRaises(BiometricKeyConfigurationError):
            TemplateCipher({"broken": b"short"}, "broken")

    def test_retention_is_required_and_bounded(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(BiometricKeyConfigurationError):
                configured_retention_days()
        with unittest.mock.patch.dict("os.environ", {"VERITY_FACE_TEMPLATE_RETENTION_DAYS": "90"}):
            self.assertEqual(configured_retention_days(), 90)
        with unittest.mock.patch.dict("os.environ", {"VERITY_FACE_TEMPLATE_RETENTION_DAYS": "0"}):
            with self.assertRaises(BiometricKeyConfigurationError):
                configured_retention_days()
