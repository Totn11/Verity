from __future__ import annotations

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.services.siamese_verifier import (
    InvalidImageError,
    ModelUnavailableError,
    SiameseVerifier,
)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class RecognitionStatus(BaseModel):
    status: str
    reason: str | None = None


class VerificationResult(BaseModel):
    matched: bool
    score: float


def _allowed_origins() -> list[str]:
    configured = os.getenv("VERITY_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


app = FastAPI(title="Verity Siamese Verification API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
verifier = SiameseVerifier.from_environment()


@app.get("/api/recognition/status", response_model=RecognitionStatus)
def recognition_status() -> RecognitionStatus:
    return RecognitionStatus(**verifier.status())


async def _read_image(upload: UploadFile) -> bytes:
    contents = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Each image must be 5 MiB or smaller.")
    return contents


@app.post("/api/recognition/verify", response_model=VerificationResult)
async def verify_images(
    probe: UploadFile = File(...),
    reference: UploadFile = File(...),
) -> VerificationResult:
    probe_bytes = await _read_image(probe)
    reference_bytes = await _read_image(reference)
    try:
        result = await run_in_threadpool(verifier.verify, probe_bytes, reference_bytes)
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=error.reason) from error
    return VerificationResult(**result)
