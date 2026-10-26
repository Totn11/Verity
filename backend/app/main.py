from __future__ import annotations

import os
import uuid
from datetime import timedelta

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.audit import (
    LOGIN_FAILURE_ACTION,
    LOGIN_SUCCESS_ACTION,
    count_recent_login_failures,
    utc_now,
)
from app.auth.dependencies import require_role, require_user
from app.auth.passwords import verify_password, verify_unknown_user_password
from app.auth.sessions import (
    COOKIE_NAME,
    create_session,
    read_session,
    revoke_session,
)
from app.auth.tokens import TokenConfigurationError
from app.api.v1.academic import router as academic_router
from app.api.v1.recognition import router as recognition_api_router
from app.api.v1.sync import router as sync_router
from app.db.models import User
from app.db.session import get_engine, get_session
from app.repositories.sql import SqlAuditRepository
from app.services.audit import AuditService
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


class SignInRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    authenticated: bool
    email: str
    user_id: str
    role: str
    expires_at: int


def _allowed_origins() -> list[str]:
    configured = os.getenv("VERITY_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


app = FastAPI(title="Verity Classroom Attendance API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Content-Type", "Idempotency-Key"],
    expose_headers=["X-Request-Id"],
    allow_credentials=True,
)
verifier = SiameseVerifier.from_environment()


@app.middleware("http")
async def assign_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


public_auth_router = APIRouter(prefix="/api/auth")
authenticated_auth_router = APIRouter(
    prefix="/api/auth",
    dependencies=[Depends(require_user)],
)
recognition_router = APIRouter(
    prefix="/api/recognition",
    dependencies=[Depends(require_role("admin", "staff"))],
)

@app.get("/api/health")
async def health() -> dict[str, str]:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, ValidationError, OSError, ModuleNotFoundError):
        return {"status": "ok", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}


@public_auth_router.post("/login", response_model=SessionResponse)
async def sign_in(
    credentials: SignInRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> SessionResponse:
    now = utc_now()
    failures = await count_recent_login_failures(
        request,
        db,
        since=now - timedelta(minutes=15),
    )
    if failures >= 5:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")

    result = await db.execute(select(User).where(User.email == credentials.email.strip()))
    user = result.scalar_one_or_none()
    valid_password = (
        verify_password(user.password_hash, credentials.password)
        if user is not None
        else False
    )
    if user is None:
        verify_unknown_user_password(credentials.password)
    if user is None or not user.is_active or not valid_password:
        await AuditService(request, SqlAuditRepository(db)).record(
            None,
            LOGIN_FAILURE_ACTION,
            "user",
            "unknown",
            {},
            {"email": credentials.email.strip(), "result": "failure"},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    before = {
        "last_login_at": user.last_login_at.isoformat()
        if user.last_login_at
        else None
    }
    user.last_login_at = now
    try:
        await create_session(user, request, response, db)
    except TokenConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    await AuditService(request, SqlAuditRepository(db)).record(
        user,
        LOGIN_SUCCESS_ACTION,
        "user",
        str(user.id),
        before,
        {"last_login_at": now.isoformat()},
    )
    response.headers["Cache-Control"] = "no-store"
    await db.commit()
    claims = request.state.auth_claims
    return SessionResponse(
        authenticated=True,
        email=user.email,
        user_id=claims["sub"],
        role=claims["role"],
        expires_at=claims["exp"],
    )


@authenticated_auth_router.get("/session", response_model=SessionResponse)
@authenticated_auth_router.get("/me", response_model=SessionResponse)
def current_session(
    request: Request,
    response: Response,
    user: User = Depends(require_user),
) -> SessionResponse:
    response.headers["Cache-Control"] = "no-store"
    claims = request.state.auth_claims
    return SessionResponse(
        authenticated=True,
        email=user.email,
        user_id=str(user.id),
        role=claims["role"],
        expires_at=claims["exp"],
    )


@public_auth_router.post("/logout", status_code=204)
async def sign_out(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> None:
    response.headers["Cache-Control"] = "no-store"
    try:
        user = await read_session(request, db)
    except TokenConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    await revoke_session(request, db)
    await AuditService(request, SqlAuditRepository(db)).record(
        user,
        "auth.logout",
        "user",
        str(user.id) if user is not None else "unknown",
        {"session_active": user is not None},
        {"session_active": False},
    )
    await db.commit()
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@app.get("/api/recognition/status", response_model=RecognitionStatus)
def recognition_status() -> RecognitionStatus:
    return RecognitionStatus(**verifier.status())


async def _read_image(upload: UploadFile) -> bytes:
    contents = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Each image must be 5 MiB or smaller.")
    return contents


@recognition_router.post("/verify", response_model=VerificationResult)
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


for router in (
    public_auth_router,
    authenticated_auth_router,
    recognition_router,
):
    app.include_router(router)

app.include_router(academic_router)
app.include_router(recognition_api_router)
app.include_router(sync_router)
