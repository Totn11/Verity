from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

IMAGE_SIZE = (100, 100)
MAX_IMAGE_DIMENSION = 4096


class InvalidImageError(ValueError):
    pass


class ModelUnavailableError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class SiameseVerifier:
    def __init__(self, model_path: Path | None, threshold: float = 0.5) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError("The model threshold must be between 0 and 1.")
        self._model_path = model_path
        self._threshold = threshold
        self._model: Any | None = None
        self._load_error: ModelUnavailableError | None = None
        self._load_lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> SiameseVerifier:
        configured_path = os.getenv("VERITY_SIAMESE_MODEL_PATH")
        model_path = Path(configured_path).expanduser() if configured_path else None
        threshold = float(os.getenv("VERITY_SIAMESE_MATCH_THRESHOLD", "0.5"))
        return cls(model_path=model_path, threshold=threshold)

    def status(self) -> dict[str, str]:
        if self._model_path is None:
            return {"status": "disabled", "reason": "model_not_configured"}
        if not self._model_path.is_file():
            return {"status": "disabled", "reason": "model_artifact_missing"}
        try:
            self._get_model()
        except ModelUnavailableError as error:
            return {"status": "unavailable", "reason": error.reason}
        return {"status": "ready"}

    def verify(self, probe_bytes: bytes, reference_bytes: bytes) -> dict[str, float | bool]:
        model = self._get_model()
        probe = preprocess_image(probe_bytes)
        reference = preprocess_image(reference_bytes)
        prediction = np.asarray(
            model.predict([probe, reference], verbose=0), dtype=np.float32
        )
        if prediction.size != 1:
            raise RuntimeError("The Siamese model returned an unexpected output shape.")
        score = float(prediction.reshape(-1)[0])
        if not np.isfinite(score) or not 0.0 <= score <= 1.0:
            raise RuntimeError("The Siamese model returned an invalid similarity score.")
        return {"matched": score >= self._threshold, "score": score}

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._model_path is None:
            raise ModelUnavailableError(
                "model_not_configured", "No Siamese model artifact is configured."
            )
        if not self._model_path.is_file():
            raise ModelUnavailableError(
                "model_artifact_missing", "The configured Siamese model artifact is missing."
            )
        if self._load_error is not None:
            raise self._load_error

        with self._load_lock:
            if self._model is not None:
                return self._model
            if self._load_error is not None:
                raise self._load_error
            try:
                import tensorflow as tf

                @tf.keras.utils.register_keras_serializable(package="Verity")
                class L1Dist(tf.keras.layers.Layer):
                    def call(self, input_embedding: Any, validation_embedding: Any) -> Any:
                        return tf.math.abs(input_embedding - validation_embedding)

                self._model = tf.keras.models.load_model(
                    self._model_path,
                    custom_objects={"L1Dist": L1Dist},
                    compile=False,
                    safe_mode=True,
                )
                expected_input_shape = (None, *IMAGE_SIZE, 3)
                input_shapes = self._model.input_shape
                output_shape = self._model.output_shape
                if (
                    not isinstance(input_shapes, list)
                    or len(input_shapes) != 2
                    or any(tuple(shape) != expected_input_shape for shape in input_shapes)
                    or output_shape not in ((None,), (None, 1))
                ):
                    raise ValueError("The artifact does not implement the expected two-image Siamese model.")
            except ImportError as error:
                self._load_error = ModelUnavailableError(
                    "inference_runtime_unavailable",
                    "TensorFlow is not installed in the backend environment.",
                )
                self._load_error.__cause__ = error
            except Exception as error:
                logger.exception("Could not load the configured Siamese model artifact.")
                self._load_error = ModelUnavailableError(
                    "model_load_failed",
                    "The configured Siamese model artifact could not be loaded.",
                )
                self._load_error.__cause__ = error
            if self._load_error is not None:
                raise self._load_error
            return self._model


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format != "JPEG":
                raise InvalidImageError("Only JPEG images are accepted.")
            width, height = image.size
            if width < 1 or height < 1 or max(width, height) > MAX_IMAGE_DIMENSION:
                raise InvalidImageError("Image dimensions are outside the supported range.")
            image.load()
            resized = image.convert("RGB").resize(IMAGE_SIZE, Image.Resampling.BILINEAR)
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise InvalidImageError("The uploaded file is not a valid JPEG image.") from error
    return np.asarray(resized, dtype=np.float32)[None, ...] / 255.0
