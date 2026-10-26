from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import time
import uuid
from collections import defaultdict
from pathlib import Path

import numpy as np
import psutil

from app.services.face_pipeline import (
    FacePipeline,
    FacePipelineError,
    assess_quality,
    match_embedding,
)


def _normalize(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(values))
    if not np.all(np.isfinite(values)) or norm <= 1e-12:
        raise ValueError("Invalid embedding returned by the configured model.")
    return values / norm


def evaluate_dataset(
    pipeline: FacePipeline,
    manifest_path: Path,
    similarity_thresholds: list[float],
    minimum_margin: float,
) -> dict:
    dataset_digest = hashlib.sha256(manifest_path.read_bytes())
    rows = []
    with manifest_path.open(newline="", encoding="utf-8") as manifest_file:
        reader = csv.DictReader(manifest_file)
        required = {"path", "identity", "split", "has_face", "lighting"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Dataset CSV must include columns: {', '.join(sorted(required))}")
        for row in reader:
            if row["split"] not in {"enrollment", "evaluation"}:
                raise ValueError("Dataset split must be 'enrollment' or 'evaluation'.")
            if row["has_face"].lower() not in {"true", "false"}:
                raise ValueError("has_face values must be true or false.")
            has_face = row["has_face"].lower() == "true"
            identity = row["identity"].strip()
            if not has_face and identity:
                raise ValueError("Images without a face must not have a student identity label.")
            if row["split"] == "enrollment" and (not has_face or not identity):
                raise ValueError("Enrollment images require one labeled face.")
            image_path = (manifest_path.parent / row["path"]).resolve()
            if not image_path.is_file():
                raise ValueError(f"Image referenced by the dataset manifest is missing: {row['path']}")
            rows.append(
                {
                    "path": image_path,
                    "identity": identity,
                    "split": row["split"],
                    "has_face": has_face,
                    "lighting": row["lighting"].strip() or "unspecified",
                }
            )

    process = psutil.Process(os.getpid())
    model_load_started = time.perf_counter()
    pipeline.load_models()
    model_load_ms = (time.perf_counter() - model_load_started) * 1000
    cpu_start = process.cpu_times()
    started = time.perf_counter()
    rss_peak = process.memory_info().rss
    embeddings_by_identity: dict[str, list[np.ndarray]] = defaultdict(list)
    evaluation: list[dict] = []
    detection_by_lighting: dict[str, dict[str, int]] = defaultdict(
        lambda: {"expected_faces": 0, "detected_faces": 0, "quality_rejected": 0}
    )
    errors: dict[str, int] = defaultdict(int)
    false_positive_detections = 0
    inference_ms: list[float] = []

    for row in rows:
        data = row["path"].read_bytes()
        dataset_digest.update(data)
        image = pipeline.decode_image(data)
        t0 = time.perf_counter()
        faces = pipeline.detector.detect(image)
        if len(faces) != 1:
            inference_ms.append((time.perf_counter() - t0) * 1000)
            errors["no_face" if not faces else "multiple_faces"] += 1
            if row["has_face"]:
                detection_by_lighting[row["lighting"]]["expected_faces"] += 1
                if faces:
                    detection_by_lighting[row["lighting"]]["detected_faces"] += 1
            elif faces:
                false_positive_detections += 1
            rss_peak = max(rss_peak, process.memory_info().rss)
            if row["split"] == "evaluation":
                evaluation.append({**row, "embedding": None})
            continue

        face = faces[0]
        x, y, face_width, face_height = (int(round(value)) for value in face[:4])
        metrics = assess_quality(image, x, y, face_width, face_height, pipeline.quality_policy)
        if row["has_face"]:
            lighting = detection_by_lighting[row["lighting"]]
            lighting["expected_faces"] += 1
            lighting["detected_faces"] += 1
        else:
            false_positive_detections += 1
        if not metrics.acceptable:
            errors["quality_rejected"] += 1
            if row["has_face"]:
                detection_by_lighting[row["lighting"]]["quality_rejected"] += 1
            inference_ms.append((time.perf_counter() - t0) * 1000)
            if row["split"] == "evaluation":
                evaluation.append({**row, "embedding": None})
            rss_peak = max(rss_peak, process.memory_info().rss)
            continue
        try:
            embedding = _normalize(pipeline.embedder.extract(image, face))
        except FacePipelineError:
            errors["embedding_error"] += 1
            inference_ms.append((time.perf_counter() - t0) * 1000)
            if row["split"] == "evaluation":
                evaluation.append({**row, "embedding": None})
            rss_peak = max(rss_peak, process.memory_info().rss)
            continue
        inference_ms.append((time.perf_counter() - t0) * 1000)
        if row["split"] == "enrollment":
            if not row["identity"]:
                raise ValueError("Enrollment images must have an identity label.")
            embeddings_by_identity[row["identity"]].append(embedding)
        else:
            evaluation.append({**row, "embedding": embedding})
        rss_peak = max(rss_peak, process.memory_info().rss)

    templates = {
        identity: _normalize(np.mean(vectors, axis=0))
        for identity, vectors in embeddings_by_identity.items()
        if vectors
    }
    if not templates:
        raise ValueError("No usable enrollment templates were produced from the dataset.")
    curve = []
    for threshold in similarity_thresholds:
        false_accepts = 0
        false_rejects = 0
        misidentifications = 0
        impostor_count = 0
        genuine_count = 0
        for row in evaluation:
            embedding = row["embedding"]
            known_identity = row["identity"] in templates
            if known_identity:
                genuine_count += 1
            elif row["has_face"]:
                impostor_count += 1
            if embedding is None:
                if known_identity:
                    false_rejects += 1
                continue
            decision = match_embedding(
                embedding, templates, threshold, minimum_margin
            )
            if known_identity:
                if decision.outcome != "matched" or decision.student_id != row["identity"]:
                    false_rejects += 1
                    if decision.outcome == "matched":
                        misidentifications += 1
            elif decision.outcome == "matched":
                false_accepts += 1
        curve.append(
            {
                "minimum_similarity": threshold,
                "minimum_margin": minimum_margin,
                "false_accept_count": false_accepts,
                "impostor_count": impostor_count,
                "false_accept_rate": false_accepts / impostor_count if impostor_count else None,
                "false_reject_count": false_rejects,
                "genuine_count": genuine_count,
                "false_reject_rate": false_rejects / genuine_count if genuine_count else None,
                "misidentification_count": misidentifications,
            }
        )

    elapsed_seconds = time.perf_counter() - started
    cpu_end = process.cpu_times()
    cpu_seconds = (cpu_end.user + cpu_end.system) - (cpu_start.user + cpu_start.system)
    valid_times = sorted(inference_ms)
    return {
        "validation_id": str(uuid.uuid4()),
        "approved_for_automatic_attendance": False,
        "approval_note": "Requires institutional review and representative consented validation data.",
        "approval": {"approved": False},
        "dataset_sha256": dataset_digest.hexdigest(),
        "detector_sha256": pipeline.detector_sha256,
        "embedder_sha256": pipeline.embedder_sha256,
        "model_version": pipeline.model_version,
        "dataset_images": len(rows),
        "enrollment_identities": len(templates),
        "evaluation_images": len(evaluation),
        "lighting_buckets": sorted(
            {row["lighting"].lower() for row in rows}
        ),
        "detection_by_lighting": {
            lighting: {
                **counts,
                "detection_rate": (
                    counts["detected_faces"] / counts["expected_faces"]
                    if counts["expected_faces"]
                    else None
                ),
            }
            for lighting, counts in sorted(detection_by_lighting.items())
        },
        "threshold_curve": curve,
        "inference_latency_ms": {
            "model_load_ms": model_load_ms,
            "sample_count": len(valid_times),
            "mean": statistics.mean(valid_times) if valid_times else None,
            "p50": float(np.percentile(valid_times, 50)) if valid_times else None,
            "p95": float(np.percentile(valid_times, 95)) if valid_times else None,
        },
        "elapsed_seconds": elapsed_seconds,
        "cpu_seconds": cpu_seconds,
        "average_cpu_percent": cpu_seconds / elapsed_seconds * 100 if elapsed_seconds else None,
        "peak_rss_bytes": rss_peak,
        "failure_counts": dict(sorted(errors.items())),
        "false_positive_detections": false_positive_detections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate YuNet/SFace on a labeled, consented local dataset; output is never auto-approved."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--minimum-margin", required=True, type=float)
    parser.add_argument("--similarity-thresholds", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--detector", type=Path, required=True)
    parser.add_argument("--embedder", type=Path, required=True)
    arguments = parser.parse_args()
    thresholds = [float(value) for value in arguments.similarity_thresholds.split(",")]
    if not thresholds or any(not 0 <= value <= 1 for value in thresholds):
        parser.error("Similarity thresholds must be comma-separated values between 0 and 1.")
    if not 0 <= arguments.minimum_margin <= 2:
        parser.error("Minimum margin must be between 0 and 2.")
    pipeline = FacePipeline(arguments.detector, arguments.embedder)
    report = evaluate_dataset(
        pipeline, arguments.manifest, thresholds, arguments.minimum_margin
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
