from __future__ import annotations

import time as monotonic_time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_role
from app.db.models import (
    AttendanceMark,
    AttendanceMethod,
    AttendanceSession,
    AttendanceSessionStatus,
    CourseEnrollment,
    FaceRecognitionAttempt,
    FaceTemplate,
    SessionAttendanceRecord,
    Student,
    User,
    UserRole,
)
from app.db.session import get_session
from app.services.audit import AuditService
from app.services.biometric_crypto import (
    BiometricKeyConfigurationError,
    EncryptedTemplateError,
    TemplateCipher,
    configured_retention_days,
)
from app.services.face_pipeline import (
    FaceModelUnavailableError,
    FacePipeline,
    FacePipelineError,
    InvalidFaceImageError,
    LowQualityFaceError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    match_embedding,
)
from app.services.recognition_policy import (
    RecognitionPolicyError,
    automatic_attendance_enabled,
    load_validated_thresholds,
)
from app.services.attendance_outbox import enqueue_attendance_event
from app.repositories.sql import SqlAuditRepository

router = APIRouter(prefix="/api/v1")
enrollment_access = require_role("admin")
recognition_access = require_role("admin", "staff", "lecturer")
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminDep = Annotated[User, Depends(enrollment_access)]
RecognizerDep = Annotated[User, Depends(recognition_access)]


class EnrollmentRead(BaseModel):
    student_id: uuid.UUID
    model_version: str
    expires_at: datetime


class RecognitionRead(BaseModel):
    outcome: str
    candidate_student_id: uuid.UUID | None
    similarity: float | None
    margin: float | None
    quality: dict[str, float | int | list[str]]
    model_version: str | None
    validation_id: str | None
    attendance_recorded: bool
    already_recorded: bool
    review_required: bool


class RecognitionStatusRead(BaseModel):
    inference_ready: bool
    enrollment_ready: bool
    validated_thresholds: bool
    automatic_attendance_enabled: bool
    reason: str | None


@lru_cache(maxsize=1)
def get_face_pipeline() -> FacePipeline:
    return FacePipeline.from_environment()


@lru_cache(maxsize=1)
def get_template_cipher() -> TemplateCipher:
    return TemplateCipher.from_environment()


async def _read_image(upload: UploadFile) -> bytes:
    contents = await upload.read(5 * 1024 * 1024 + 1)
    if not contents or len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be non-empty and no larger than 5 MiB.")
    return contents


async def _require_section_access(
    db: AsyncSession, session: AttendanceSession, actor: User
) -> None:
    if actor.role != UserRole.LECTURER:
        return
    from app.db.models import ClassSection

    section = await db.get(ClassSection, session.class_section_id)
    if section is None or section.lecturer_user_id != actor.id:
        raise HTTPException(status_code=403, detail="This class section is not assigned to the lecturer.")


async def _record_attempt(
    db: AsyncSession,
    actor: User,
    session_id: uuid.UUID,
    outcome: str,
    inference_ms: int,
    quality: dict[str, float | int | list[str]],
    model_version: str | None,
    detector_sha256: str | None,
    embedder_sha256: str | None,
) -> None:
    db.add(
        FaceRecognitionAttempt(
            session_id=session_id,
            actor_user_id=actor.id,
            outcome=outcome,
            model_version=model_version or "unavailable",
            detector_sha256=detector_sha256,
            embedder_sha256=embedder_sha256,
            inference_ms=max(0, inference_ms),
            quality_metrics=quality,
        )
    )
    await db.commit()


@router.get("/recognition/status", response_model=RecognitionStatusRead)
async def recognition_status(actor: RecognizerDep) -> RecognitionStatusRead:
    try:
        pipeline = get_face_pipeline()
        await run_in_threadpool(pipeline.load_models)
    except FaceModelUnavailableError:
        return RecognitionStatusRead(
            inference_ready=False,
            enrollment_ready=False,
            validated_thresholds=False,
            automatic_attendance_enabled=False,
            reason="face_models_unavailable",
        )
    try:
        cipher = get_template_cipher()
        retention_days = configured_retention_days()
        del cipher
    except BiometricKeyConfigurationError:
        return RecognitionStatusRead(
            inference_ready=True,
            enrollment_ready=False,
            validated_thresholds=False,
            automatic_attendance_enabled=False,
            reason="encryption_or_retention_not_configured",
        )
    try:
        thresholds = load_validated_thresholds(pipeline)
    except RecognitionPolicyError:
        return RecognitionStatusRead(
            inference_ready=True,
            enrollment_ready=True,
            validated_thresholds=False,
            automatic_attendance_enabled=False,
            reason="validation_manifest_invalid",
        )
    approved = thresholds is not None
    return RecognitionStatusRead(
        inference_ready=True,
        enrollment_ready=True,
        validated_thresholds=approved,
        automatic_attendance_enabled=approved and automatic_attendance_enabled(),
        reason=None if approved else "thresholds_not_validated;manual_review_only",
    )


@router.post(
    "/students/{student_id}/face-template",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def enroll_face_template(
    student_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    actor: AdminDep,
    image: Annotated[UploadFile, File(...)],
    consent_confirmed: Annotated[bool, Form(...)],
    consent_record_id: Annotated[str, Form(min_length=1, max_length=255)],
) -> EnrollmentRead:
    student = await db.get(Student, student_id)
    if student is None or not student.is_active:
        raise HTTPException(status_code=404, detail="Active student not found.")
    if not consent_confirmed or not consent_record_id.strip():
        raise HTTPException(
            status_code=422,
            detail="Explicit consent confirmation and an institutional consent reference are required.",
        )
    existing = await db.scalar(
        select(FaceTemplate.id).where(FaceTemplate.student_id == student_id)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="A face template already exists for this student.")
    try:
        retention_days = configured_retention_days()
        cipher = get_template_cipher()
        pipeline = get_face_pipeline()
        observation = await run_in_threadpool(pipeline.infer, await _read_image(image))
    except BiometricKeyConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FaceModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except InvalidFaceImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except NoFaceDetectedError as error:
        raise HTTPException(status_code=422, detail="No face was detected; use manual attendance.") from error
    except MultipleFacesDetectedError as error:
        raise HTTPException(status_code=422, detail="Show only the consenting student's face.") from error
    except LowQualityFaceError as error:
        raise HTTPException(
            status_code=422,
            detail={"message": str(error), "quality": error.metrics.safe_metrics()},
        ) from error
    except FacePipelineError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    now = datetime.now(UTC)
    expiry = now + timedelta(days=retention_days)
    encrypted = cipher.encrypt(observation.embedding, student_id, observation.model_version)
    template = FaceTemplate(
        student_id=student_id,
        encrypted_template=encrypted.ciphertext,
        encryption_key_id=encrypted.key_id,
        model_version=observation.model_version,
        model_sha256=observation.embedder_sha256,
        consented_at=now,
        consent_record_id=consent_record_id.strip(),
        consent_actor_user_id=actor.id,
        expires_at=expiry,
    )
    db.add(template)
    await db.flush()
    response = EnrollmentRead(
        student_id=student_id,
        model_version=observation.model_version,
        expires_at=expiry,
    )
    await AuditService(request, SqlAuditRepository(db)).record(
        actor,
        "face_templates.create",
        "face_template",
        str(template.id),
        {},
        {
            "student_id": str(student_id),
            "consent_record_id": consent_record_id.strip(),
            "model_version": observation.model_version,
            "expires_at": expiry.isoformat(),
        },
    )
    await db.commit()
    return response


@router.delete("/students/{student_id}/face-template", status_code=status.HTTP_204_NO_CONTENT)
async def delete_face_template(
    student_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    actor: AdminDep,
) -> None:
    template = await db.scalar(
        select(FaceTemplate).where(FaceTemplate.student_id == student_id)
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Face template not found.")
    await AuditService(request, SqlAuditRepository(db)).record(
        actor,
        "face_templates.delete",
        "face_template",
        str(template.id),
        {
            "student_id": str(student_id),
            "model_version": template.model_version,
            "consent_record_id": template.consent_record_id,
        },
        {"deleted": True},
    )
    await db.delete(template)
    await db.commit()


@router.post(
    "/attendance-sessions/{session_id}/recognize",
    response_model=RecognitionRead,
)
async def recognize_for_session(
    session_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    actor: RecognizerDep,
    image: Annotated[UploadFile, File(...)],
) -> RecognitionRead:
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    await _require_section_access(db, session, actor)
    if session.status != AttendanceSessionStatus.OPEN:
        raise HTTPException(status_code=409, detail="Recognition is available only during an open session.")

    started = monotonic_time.perf_counter()
    model: FacePipeline | None = None
    outcome = "error"
    quality: dict[str, float | int | list[str]] = {"warnings": []}
    try:
        model = get_face_pipeline()
        observation = await run_in_threadpool(model.infer, await _read_image(image))
        quality = observation.quality.safe_metrics()
        cipher = get_template_cipher()
        rows = await db.execute(
            select(Student.id, FaceTemplate)
            .join(CourseEnrollment, CourseEnrollment.student_id == Student.id)
            .join(FaceTemplate, FaceTemplate.student_id == Student.id)
            .where(
                CourseEnrollment.class_section_id == session.class_section_id,
                Student.is_active.is_(True),
                FaceTemplate.revoked_at.is_(None),
                FaceTemplate.consent_record_id.is_not(None),
                FaceTemplate.model_version == observation.model_version,
                or_(FaceTemplate.expires_at.is_(None), FaceTemplate.expires_at > datetime.now(UTC)),
            )
        )
        templates: dict[str, np.ndarray] = {}
        for student_id, template in rows.all():
            templates[str(student_id)] = cipher.decrypt(
                template.encrypted_template,
                template.encryption_key_id,
                student_id,
                template.model_version,
            )
        thresholds = load_validated_thresholds(model)
        decision = match_embedding(
            observation.embedding,
            templates,
            thresholds.minimum_similarity if thresholds else None,
            thresholds.minimum_margin if thresholds else None,
        )
        outcome = decision.outcome
        attendance_recorded = False
        already_recorded = False
        automatic = thresholds is not None and automatic_attendance_enabled()
        if decision.outcome == "matched" and decision.student_id and automatic:
            student_id = uuid.UUID(decision.student_id)
            existing_record = await db.scalar(
                select(SessionAttendanceRecord).where(
                    SessionAttendanceRecord.session_id == session_id,
                    SessionAttendanceRecord.student_id == student_id,
                )
            )
            if existing_record is not None:
                already_recorded = True
            else:
                event_id = f"face:{uuid.uuid4()}"
                marked_at = datetime.now(UTC)
                record = SessionAttendanceRecord(
                    session_id=session_id,
                    student_id=student_id,
                    mark=AttendanceMark.PRESENT,
                    method=AttendanceMethod.FACE_RECOGNITION,
                    confidence=(
                        Decimal(str(decision.best_similarity))
                        if decision.best_similarity is not None
                        else None
                    ),
                    source_event_id=event_id,
                    marked_at=marked_at,
                    actor_user_id=actor.id,
                )
                db.add(record)
                try:
                    await db.flush()
                    enqueue_attendance_event(
                        db,
                        source_event_id=event_id,
                        session_id=session_id,
                        student_id=student_id,
                        mark=AttendanceMark.PRESENT.value,
                        marked_at=marked_at,
                        actor_user_id=actor.id,
                    )
                    from app.api.v1.academic import AttendanceRecordRead

                    await AuditService(request, SqlAuditRepository(db)).record(
                        actor,
                        "attendance_records.face_recognition",
                        "attendance_record",
                        str(record.id),
                        {},
                        AttendanceRecordRead.model_validate(record).model_dump(mode="json"),
                    )
                    await db.commit()
                    attendance_recorded = True
                except IntegrityError as error:
                    await db.rollback()
                    existing_record = await db.scalar(
                        select(SessionAttendanceRecord).where(
                            SessionAttendanceRecord.session_id == session_id,
                            SessionAttendanceRecord.student_id == student_id,
                        )
                    )
                    if existing_record is None:
                        outcome = "error"
                        raise HTTPException(
                            status_code=409,
                            detail="Attendance could not be recorded because the session data conflicted.",
                        ) from error
                    already_recorded = True
        return RecognitionRead(
            outcome=decision.outcome,
            candidate_student_id=uuid.UUID(decision.student_id) if decision.student_id else None,
            similarity=decision.best_similarity,
            margin=decision.margin,
            quality=quality,
            model_version=observation.model_version,
            validation_id=thresholds.validation_id if thresholds else None,
            attendance_recorded=attendance_recorded,
            already_recorded=already_recorded,
            review_required=decision.outcome != "matched" or not automatic,
        )
    except LowQualityFaceError as error:
        outcome = "quality_rejected"
        quality = error.metrics.safe_metrics()
        raise HTTPException(status_code=422, detail={"message": str(error), "quality": quality}) from error
    except NoFaceDetectedError as error:
        outcome = "no_face"
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MultipleFacesDetectedError as error:
        outcome = "multiple_faces"
        raise HTTPException(status_code=422, detail=str(error)) from error
    except InvalidFaceImageError as error:
        outcome = "error"
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FaceModelUnavailableError as error:
        outcome = "model_unavailable"
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (BiometricKeyConfigurationError, EncryptedTemplateError) as error:
        outcome = "error"
        raise HTTPException(status_code=503, detail=str(error)) from error
    except RecognitionPolicyError as error:
        outcome = "error"
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FacePipelineError as error:
        outcome = "error"
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        await _record_attempt(
            db,
            actor,
            session_id,
            outcome,
            round((monotonic_time.perf_counter() - started) * 1000),
            quality,
            model.model_version if model else None,
            model.detector_sha256 if model else None,
            model.embedder_sha256 if model else None,
        )
