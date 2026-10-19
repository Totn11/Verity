from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
from PIL import Image
import tensorflow as tf

from app.services.siamese_verifier import (
    InvalidImageError,
    SiameseVerifier,
    preprocess_image,
)


def jpeg_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (120, 80), color=(128, 64, 32)).save(output, format="JPEG")
    return output.getvalue()


class SiameseVerifierTests(unittest.TestCase):
    def test_model_is_disabled_without_an_artifact(self) -> None:
        verifier = SiameseVerifier(model_path=None)
        self.assertEqual(
            verifier.status(),
            {"status": "disabled", "reason": "model_not_configured"},
        )

    def test_model_is_disabled_when_artifact_is_missing(self) -> None:
        verifier = SiameseVerifier(model_path=Path("/missing/siamesemodel.h5"))
        self.assertEqual(
            verifier.status(),
            {"status": "disabled", "reason": "model_artifact_missing"},
        )

    def test_environment_does_not_enable_model_without_explicit_path(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                SiameseVerifier.from_environment().status(),
                {"status": "disabled", "reason": "model_not_configured"},
            )

    def test_preprocessing_matches_notebook_shape_and_scaling(self) -> None:
        result = preprocess_image(jpeg_bytes())
        self.assertEqual(result.shape, (1, 100, 100, 3))
        self.assertEqual(result.dtype, np.float32)
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)

    def test_preprocessing_rejects_non_jpeg_images(self) -> None:
        output = io.BytesIO()
        Image.new("RGB", (10, 10)).save(output, format="PNG")
        with self.assertRaisesRegex(InvalidImageError, "Only JPEG"):
            preprocess_image(output.getvalue())

    def test_loads_notebook_style_h5_model_and_returns_pair_score(self) -> None:
        class L1Dist(tf.keras.layers.Layer):
            def call(self, input_embedding: Any, validation_embedding: Any) -> Any:
                return tf.math.abs(input_embedding - validation_embedding)

        probe_input = tf.keras.Input(shape=(100, 100, 3))
        reference_input = tf.keras.Input(shape=(100, 100, 3))
        distance = L1Dist()(probe_input, reference_input)
        pooled = tf.keras.layers.GlobalAveragePooling2D()(distance)
        output = tf.keras.layers.Dense(1, activation="sigmoid")(pooled)
        model = tf.keras.Model([probe_input, reference_input], output)

        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "siamesemodel.h5"
            model.save(model_path)
            verifier = SiameseVerifier(model_path=model_path)

            self.assertEqual(verifier.status(), {"status": "ready"})
            result = verifier.verify(jpeg_bytes(), jpeg_bytes())

        self.assertIsInstance(result["matched"], bool)
        self.assertGreaterEqual(float(result["score"]), 0.0)
        self.assertLessEqual(float(result["score"]), 1.0)


if __name__ == "__main__":
    unittest.main()
