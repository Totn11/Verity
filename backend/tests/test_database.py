from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base, NAMING_CONVENTION
from app.db.config import get_settings
from app.db.models import (
    AttendanceEvent,
    AttendanceSession,
    Course,
    CourseEnrollment,
    FaceTemplate,
    LocationEvent,
    Person,
    Room,
    Session,
    SessionAttendanceRecord,
    Student,
    User,
)
from app.db.session import get_engine
from app.main import app, health


class DatabaseLayerTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()
        get_engine.cache_clear()

    def test_database_url_is_required_and_loaded_from_environment(self) -> None:
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                get_settings()

        get_settings.cache_clear()
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://example"}, clear=True):
            self.assertEqual(get_settings().database_url, "postgresql+asyncpg://example")

    def test_base_contains_classroom_models_and_preserves_legacy_tables(self) -> None:
        self.assertEqual(
            set(Base.metadata.tables),
            {
                "users",
                "sessions",
                "people",
                "rooms",
                "attendance_events",
                "recognition_events",
                "location_events",
                "audit_events",
                "students",
                "semesters",
                "courses",
                "class_sections",
                "course_enrollments",
                "attendance_sessions",
                "session_attendance_records",
                "face_templates",
                "face_recognition_attempts",
                "attendance_sync_outbox",
            },
        )
        self.assertEqual(Base.metadata.naming_convention, NAMING_CONVENTION)

    def test_requested_relationships_indexes_and_sensitive_data_exclusions(self) -> None:
        self.assertIsNotNone(User.sessions.property.back_populates)
        self.assertIsNotNone(Session.user.property.back_populates)
        self.assertIsNotNone(Person.attendance_events.property.back_populates)
        self.assertIsNotNone(Room.location_events.property.back_populates)
        self.assertIsNotNone(Student.enrollments.property.back_populates)
        self.assertIsNotNone(Course.class_sections.property.back_populates)
        self.assertIsNotNone(CourseEnrollment.student.property.back_populates)
        self.assertIsNotNone(AttendanceSession.records.property.back_populates)
        self.assertIsNotNone(SessionAttendanceRecord.student.property.back_populates)
        self.assertIsNotNone(FaceTemplate.student.property.back_populates)
        self.assertEqual(
            {
                index.name
                for index in SessionAttendanceRecord.__table__.indexes
                if index.unique
            },
            {"uq_session_attendance_session_student", "uq_session_attendance_source_event"},
        )
        self.assertEqual(
            {column.name for column in FaceTemplate.__table__.columns}
            & {"encrypted_template", "encryption_key_id", "model_sha256", "consent_record_id"},
            {"encrypted_template", "encryption_key_id", "model_sha256", "consent_record_id"},
        )
        self.assertEqual(
            {index.name for index in AttendanceEvent.__table__.indexes},
            {
                "ix_attendance_events_person_occurred_at",
                "uq_attendance_events_source_event_id",
            },
        )
        self.assertEqual(
            {index.name for index in LocationEvent.__table__.indexes},
            {
                "ix_location_events_person_occurred_at",
                "uq_location_events_source_event_id",
            },
        )
        for table in Base.metadata.tables.values():
            self.assertFalse(
                {"image_bytes", "biometric_template", "embedding"}.intersection(
                    table.columns.keys()
                )
            )

    def test_health_returns_ok_when_select_succeeds(self) -> None:
        connection = AsyncMock()
        engine = Mock()
        engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
        engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.main.get_engine", return_value=engine):
            self.assertEqual(
                asyncio.run(health()),
                {"status": "ok", "database": "ok"},
            )
        connection.execute.assert_awaited_once()

    def test_health_reports_unavailable_when_database_fails(self) -> None:
        connection = AsyncMock()
        connection.execute.side_effect = SQLAlchemyError("database unavailable")
        engine = Mock()
        engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
        engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("app.main.get_engine", return_value=engine):
            response = TestClient(app).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "unavailable"})

    def test_health_reports_unavailable_when_database_url_is_missing(self) -> None:
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                asyncio.run(health()),
                {"status": "ok", "database": "unavailable"},
            )

    def test_auth_session_returns_service_unavailable_when_database_url_is_missing(self) -> None:
        get_settings.cache_clear()
        get_engine.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            response = TestClient(app).get("/api/auth/session")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": "Database is not configured. Set DATABASE_URL to enable authentication."
            },
        )


if __name__ == "__main__":
    unittest.main()
