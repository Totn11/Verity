from __future__ import annotations

import hashlib
import math
import io
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
EXPECTED_EMBEDDING_SIZE = 128


class FacePipelineError(RuntimeError):
    pass


class InvalidFaceImageError(ValueError):
    pass


class NoFaceDetectedError(FacePipelineError):
    pass


class MultipleFacesDetectedError(FacePipelineError):
    pass


class LowQualityFaceError(FacePipelineError):
    def __init__(self, metrics: ImageQuality) -> None:
        super().__init__("Image quality is below the configured minimum.")
        self.metrics = metrics


class FaceModelUnavailableError(FacePipelineError):
    pass


@dataclass(frozen=True)
class QualityPolicy:
    minimum_brightness: float = 28.0
    minimum_contrast: float = 12.0
    minimum_blur_variance: float = 25.0
    minimum_face_dimension: int = 80

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.minimum_brightness)
            or not 0.0 <= self.minimum_brightness <= 255.0
            or not math.isfinite(self.minimum_contrast)
            or not 0.0 <= self.minimum_contrast <= 127.5
            or not math.isfinite(self.minimum_blur_variance)
            or self.minimum_blur_variance < 0.0
            or not 1 <= self.minimum_face_dimension <= MAX_IMAGE_DIMENSION
        ):
            raise ValueError("Image-quality thresholds are outside their supported ranges.")

    @classmethod
    def from_environment(cls) -> QualityPolicy:
        return cls(
            minimum_brightness=float(os.getenv("VERITY_FACE_MIN_BRIGHTNESS", "28")),
            minimum_contrast=float(os.getenv("VERITY_FACE_MIN_CONTRAST", "12")),
            minimum_blur_variance=float(os.getenv("VERITY_FACE_MIN_BLUR_VARIANCE", "25")),
            minimum_face_dimension=int(os.getenv("VERITY_FACE_MIN_DIMENSION", "80")),
        )


@dataclass(frozen=True)
class ImageQuality:
    brightness_mean: float
    contrast_stddev: float
    blur_variance: float
    face_width: int
    face_height: int
    warnings: tuple[str, ...]

    @property
    def acceptable(self) -> bool:
        return not self.warnings

    def safe_metrics(self) -> dict[str, float | int | list[str]]:
        return {
            "brightness_mean": round(self.brightness_mean, 2),
            "contrast_stddev": round(self.contrast_stddev, 2),
            "blur_variance": round(self.blur_variance, 2),
            "face_width": self.face_width,
            "face_height": self.face_height,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class FaceObservation:
    embedding: np.ndarray
    quality: ImageQuality
    model_version: str
    detector_sha256: str
    embedder_sha256: str


@dataclass(frozen=True)
class MatchDecision:
    outcome: str
    student_id: str | None
    best_similarity: float | None
    margin: float | None


class YuNetFaceDetector:
    def __init__(
        self,
        model_path: Path,
        score_threshold: float = 0.8,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ) -> None:
        if (
            not math.isfinite(score_threshold)
            or not 0.0 <= score_threshold <= 1.0
            or not math.isfinite(nms_threshold)
            or not 0.0 <= nms_threshold <= 1.0
            or top_k < 1
        ):
            raise ValueError("YuNet detector configuration is invalid.")
        self.model_path = model_path
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self._model: Any | None = None
        self._load_lock = threading.Lock()

    def load(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.model_path.is_file():
            raise FaceModelUnavailableError("The configured YuNet detector artifact is missing.")
        with self._load_lock:
            if self._model is None:
                try:
                    cv2.setNumThreads(max(1, int(os.getenv("VERITY_OPENCV_THREADS", "1"))))
                    self._model = cv2.FaceDetectorYN.create(
                        str(self.model_path),
                        "",
                        (320, 320),
                        self.score_threshold,
                        self.nms_threshold,
                        self.top_k,
                    )
                except (cv2.error, AttributeError, ValueError) as error:
                    raise FaceModelUnavailableError(
                        "OpenCV could not load the configured YuNet detector."
                    ) from error
        return self._model

    def detect(self, image: np.ndarray) -> tuple[np.ndarray, ...]:
        height, width = image.shape[:2]
        detector = self.load()
        detector.setInputSize((width, height))
        result = detector.detect(image)
        faces = result[1] if isinstance(result, tuple) else result
        if faces is None:
            return ()
        return tuple(np.asarray(face, dtype=np.float32) for face in faces)


class SFaceEmbedder:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._model: Any | None = None
        self._load_lock = threading.Lock()

    def load(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.model_path.is_file():
            raise FaceModelUnavailableError("The configured SFace embedding artifact is missing.")
        with self._load_lock:
            if self._model is None:
                try:
                    self._model = cv2.FaceRecognizerSF.create(str(self.model_path), "")
                except (cv2.error, AttributeError, ValueError) as error:
                    raise FaceModelUnavailableError(
                        "OpenCV could not load the configured SFace embedder."
                    ) from error
        return self._model

    def extract(self, image: np.ndarray, face: np.ndarray) -> np.ndarray:
        model = self.load()
        try:
            aligned = model.alignCrop(image, face)
            feature = np.asarray(model.feature(aligned), dtype=np.float32).reshape(-1)
        except cv2.error as error:
            raise FacePipelineError("Face alignment or embedding inference failed.") from error
        if feature.shape != (EXPECTED_EMBEDDING_SIZE,) or not np.all(np.isfinite(feature)):
            raise FacePipelineError("The embedding model returned an invalid vector.")
        norm = float(np.linalg.norm(feature))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise FacePipelineError("The embedding model returned a zero vector.")
        return feature / norm


class FacePipeline:
    """YuNet detection and SFace MobileFaceNet embedding on OpenCV's CPU DNN."""

    def __init__(
        self,
        detector_path: Path,
        embedder_path: Path,
        quality_policy: QualityPolicy | None = None,
        detector_score_threshold: float = 0.8,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ) -> None:
        if (
            not math.isfinite(detector_score_threshold)
            or not 0.0 <= detector_score_threshold <= 1.0
            or not math.isfinite(nms_threshold)
            or not 0.0 <= nms_threshold <= 1.0
            or top_k < 1
        ):
            raise ValueError("YuNet detector configuration is invalid.")
        self.detector_path = detector_path
        self.embedder_path = embedder_path
        self.quality_policy = quality_policy or QualityPolicy.from_environment()
        self.detector_score_threshold = detector_score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self._detector_sha256 = self._sha256(detector_path)
        self._embedder_sha256 = self._sha256(embedder_path)
        self.detector = YuNetFaceDetector(
            detector_path, detector_score_threshold, nms_threshold, top_k
        )
        self.embedder = SFaceEmbedder(embedder_path)
        self.model_version = (
            f"yunet-2023mar+sface-2021dec:"
            f"{self._detector_sha256[:12]}:{self._embedder_sha256[:12]}"
        )
        self.detector_sha256 = self._detector_sha256
        self.embedder_sha256 = self._embedder_sha256

    @classmethod
    def from_environment(cls) -> FacePipeline:
        detector = os.getenv("VERITY_YUNET_MODEL_PATH")
        embedder = os.getenv("VERITY_SFACE_MODEL_PATH")
        if not detector or not embedder:
            raise FaceModelUnavailableError(
                "Set VERITY_YUNET_MODEL_PATH and VERITY_SFACE_MODEL_PATH to install model artifacts."
            )
        try:
            quality_policy = QualityPolicy.from_environment()
        except ValueError as error:
            raise FaceModelUnavailableError("Image-quality threshold configuration is invalid.") from error
        return cls(
            Path(detector).expanduser(),
            Path(embedder).expanduser(),
            quality_policy=quality_policy,
        )

    def infer(self, image_bytes: bytes) -> FaceObservation:
        image = self.decode_image(image_bytes)
        faces = self.detector.detect(image)
        if not faces:
            raise NoFaceDetectedError("No face was detected.")
        if len(faces) != 1:
            raise MultipleFacesDetectedError("Exactly one face must be visible for this operation.")

        face = faces[0]
        x, y, face_width, face_height = (int(round(value)) for value in face[:4])
        quality = assess_quality(image, x, y, face_width, face_height, self.quality_policy)
        if not quality.acceptable:
            raise LowQualityFaceError(quality)
        feature = np.asarray(self.embedder.extract(image, face), dtype=np.float32).reshape(-1)
        if feature.shape != (EXPECTED_EMBEDDING_SIZE,) or not np.all(np.isfinite(feature)):
            raise FacePipelineError("The embedding model returned an invalid vector.")
        norm = float(np.linalg.norm(feature))
        if norm <= 1e-12:
            raise FacePipelineError("The embedding model returned a zero vector.")
        feature = feature / norm
        return FaceObservation(
            embedding=feature,
            quality=quality,
            model_version=self.model_version,
            detector_sha256=self._detector_sha256,
            embedder_sha256=self._embedder_sha256,
        )

    def load_models(self) -> None:
        self.detector.load()
        self.embedder.load()

    @staticmethod
    def decode_image(image_bytes: bytes) -> np.ndarray:
        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            raise InvalidFaceImageError("Image is empty or exceeds the 5 MiB limit.")
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP"):
                    raise InvalidFaceImageError("Only JPEG, PNG, and WEBP images are accepted.")
                width, height = image.size
                if (
                    width < 1
                    or height < 1
                    or max(width, height) > MAX_IMAGE_DIMENSION
                    or width * height > 12_000_000
                ):
                    raise InvalidFaceImageError("Image dimensions are outside the supported range.")
                image.load()
                encoded = io.BytesIO()
                image.convert("RGB").save(encoded, format="JPEG", quality=95)
        except InvalidFaceImageError:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise InvalidFaceImageError("The uploaded file is not a valid image.") from error
        decoded = cv2.imdecode(np.frombuffer(encoded.getvalue(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise InvalidFaceImageError("OpenCV could not decode the uploaded image.")
        return decoded

    @staticmethod
    def _sha256(path: Path) -> str:
        if not path.is_file():
            raise FaceModelUnavailableError(f"Model artifact is missing: {path.name}")
        digest = hashlib.sha256()
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


def assess_quality(
    image: np.ndarray,
    x: int,
    y: int,
    face_width: int,
    face_height: int,
    policy: QualityPolicy,
) -> ImageQuality:
    image_height, image_width = image.shape[:2]
    warnings = []
    if (
        x < 0
        or y < 0
        or face_width <= 0
        or face_height <= 0
        or x + face_width > image_width
        or y + face_height > image_height
    ):
        warnings.append("face_out_of_frame")
    left = max(0, x)
    top = max(0, y)
    right = min(image_width, x + max(0, face_width))
    bottom = min(image_height, y + max(0, face_height))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        crop = image
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if brightness < policy.minimum_brightness:
        warnings.append("low_brightness")
    if contrast < policy.minimum_contrast:
        warnings.append("low_contrast")
    if blur < policy.minimum_blur_variance:
        warnings.append("blur")
    if min(face_width, face_height) < policy.minimum_face_dimension:
        warnings.append("face_too_small")
    return ImageQuality(
        brightness_mean=brightness,
        contrast_stddev=contrast,
        blur_variance=blur,
        face_width=face_width,
        face_height=face_height,
        warnings=tuple(warnings),
    )


def match_embedding(
    probe: np.ndarray,
    templates: dict[str, np.ndarray],
    minimum_similarity: float | None,
    minimum_margin: float | None,
) -> MatchDecision:
    if minimum_similarity is None or minimum_margin is None or not templates:
        return MatchDecision("uncertain", None, None, None)
    if (
        not math.isfinite(minimum_similarity)
        or not 0.0 <= minimum_similarity <= 1.0
        or not math.isfinite(minimum_margin)
        or not 0.0 <= minimum_margin <= 2.0
    ):
        raise ValueError("Recognition thresholds are outside their supported ranges.")
    probe_vector = np.asarray(probe, dtype=np.float32).reshape(-1)
    if probe_vector.shape != (EXPECTED_EMBEDDING_SIZE,) or not np.all(np.isfinite(probe_vector)):
        raise ValueError("Probe embedding has an invalid shape or value.")
    norm = float(np.linalg.norm(probe_vector))
    if norm <= 1e-12:
        raise ValueError("Probe embedding must be non-zero.")
    probe_vector = probe_vector / norm
    similarities = []
    for student_id, embedding in templates.items():
        candidate = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if candidate.shape != probe_vector.shape or not np.all(np.isfinite(candidate)):
            raise ValueError("A stored template has an invalid shape or value.")
        candidate_norm = float(np.linalg.norm(candidate))
        if candidate_norm <= 1e-12:
            raise ValueError("A stored template must be non-zero.")
        similarity = float(np.dot(probe_vector, candidate / candidate_norm))
        similarities.append((similarity, student_id))
    similarities.sort(reverse=True)
    best_similarity, best_id = similarities[0]
    second_similarity = similarities[1][0] if len(similarities) > 1 else -1.0
    margin = best_similarity - second_similarity
    if best_similarity < minimum_similarity or margin < minimum_margin:
        return MatchDecision("uncertain", None, best_similarity, margin)
    return MatchDecision("matched", best_id, best_similarity, margin)
