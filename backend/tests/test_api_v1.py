from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.api.v1.academic import (
    AttendanceRecordInput,
    AttendanceSessionInput,
    SectionInput,
)
from app.db.models import AttendanceMethod, AttendanceSessionStatus
from app.main import app


def test_classroom_api_is_registered_and_legacy_facility_routes_are_removed() -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods or set()
    }

    assert ("GET", "/api/v1/dashboard/summary") in routes
    assert ("POST", "/api/v1/students") in routes
    assert ("POST", "/api/v1/students/{student_id}/face-template") in routes
    assert ("DELETE", "/api/v1/students/{student_id}/face-template") in routes
    assert ("POST", "/api/v1/attendance-sessions/{session_id}/recognize") in routes
    assert ("GET", "/api/v1/recognition/status") in routes
    assert ("POST", "/api/v1/sync/attendance") in routes
    assert ("POST", "/api/v1/class-sections/{section_id}/attendance-sessions") in routes
    assert ("PATCH", "/api/v1/attendance-sessions/{session_id}/records/{record_id}") in routes
    assert ("GET", "/api/v1/attendance-sessions/{session_id}/records.csv") in routes
    assert not any(path.startswith("/api/v1/rooms") for _, path in routes)
    assert not any(path.startswith("/api/v1/people") for _, path in routes)
    assert not any(path == "/api/v1/attendance/check-in" for _, path in routes)


def test_class_section_schedule_requires_day_and_both_times() -> None:
    with pytest.raises(ValidationError, match="must be provided together"):
        SectionInput(
            course_id="00000000-0000-0000-0000-000000000001",
            semester_id="00000000-0000-0000-0000-000000000002",
            section_code="A",
            schedule_weekday=2,
        )


def test_class_section_schedule_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError, match="must be after"):
        SectionInput(
            course_id="00000000-0000-0000-0000-000000000001",
            semester_id="00000000-0000-0000-0000-000000000002",
            section_code="A",
            schedule_weekday=2,
            schedule_starts_at="11:00",
            schedule_ends_at="10:00",
        )


def test_attendance_input_refuses_nonmanual_methods_until_enabled() -> None:
    with pytest.raises(ValidationError, match="Only manual attendance recording"):
        AttendanceRecordInput(
            student_id="00000000-0000-0000-0000-000000000001",
            method=AttendanceMethod.FACE_RECOGNITION,
        )


def test_scheduled_session_requires_future_timezone_aware_time() -> None:
    with pytest.raises(ValidationError, match="future start time"):
        AttendanceSessionInput(
            status=AttendanceSessionStatus.SCHEDULED,
            scheduled_for=datetime.now(UTC) - timedelta(minutes=1),
        )
    with pytest.raises(ValidationError, match="must include a timezone"):
        AttendanceSessionInput(
            status=AttendanceSessionStatus.SCHEDULED,
            scheduled_for=datetime(2030, 1, 1, 10),
        )
