from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.auth.dependencies import require_user
from app.db.models import User, UserRole
from app.db.session import get_session
from app.main import app


def test_staff_cannot_enroll_or_delete_biometric_templates() -> None:
    staff = User(id=uuid.uuid4(), role=UserRole.STAFF)

    async def current_staff() -> User:
        return staff

    async def unused_session():
        yield object()

    app.dependency_overrides[require_user] = current_staff
    app.dependency_overrides[get_session] = unused_session
    try:
        with TestClient(app) as client:
            student_id = uuid.uuid4()
            enroll = client.post(f"/api/v1/students/{student_id}/face-template")
            delete = client.delete(f"/api/v1/students/{student_id}/face-template")
        assert enroll.status_code == 403
        assert delete.status_code == 403
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(get_session, None)
