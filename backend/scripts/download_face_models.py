from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen

OPENCV_ZOO_COMMIT = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
REPOSITORY = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{OPENCV_ZOO_COMMIT}"
ARTIFACTS = {
    "face_detection_yunet_2023mar.onnx": (
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        232589,
    ),
    "face_recognition_sface_2021dec.onnx": (
        "models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        38696353,
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_artifact(destination: Path, relative_path: str, expected_hash: str, size: int) -> None:
    if destination.is_file():
        if destination.stat().st_size == size and sha256(destination) == expected_hash:
            print(f"Verified existing model: {destination}")
            return
        raise RuntimeError(f"Existing model artifact failed checksum verification: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with urlopen(f"{REPOSITORY}/{relative_path}", timeout=60) as response:
                count = 0
                digest = hashlib.sha256()
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > size:
                        raise RuntimeError("Downloaded model exceeds the pinned artifact size.")
                    digest.update(chunk)
                    temporary.write(chunk)
        if count != size or digest.hexdigest() != expected_hash:
            raise RuntimeError(f"Model checksum or size mismatch for {destination.name}.")
        os.replace(temporary_path, destination)
        print(f"Downloaded and verified model: {destination}")
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> None:
    default_directory = Path(__file__).resolve().parents[2] / "model-artifacts"
    output_directory = Path(
        os.getenv("VERITY_MODEL_ARTIFACT_DIRECTORY", str(default_directory))
    ).expanduser()
    for name, (relative_path, expected_hash, size) in ARTIFACTS.items():
        install_artifact(output_directory / name, relative_path, expected_hash, size)


if __name__ == "__main__":
    main()
