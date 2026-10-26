from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.error import HTTPError, URLError

from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.sync import AttendanceSyncInput, _authorized_sync_request
from app.services.attendance_outbox import enqueue_attendance_event, sync_pending_outbox


def _source_event_id() -> str:
    return str(uuid.uuid4())


def test_outbox_event_is_idempotent_and_contains_only_attendance_fields() -> None:
    db = Mock()
    event_id = _source_event_id()
    session_id = uuid.uuid4()
    student_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    marked_at = datetime.now(UTC)

    event = enqueue_attendance_event(
        db,
        source_event_id=event_id,
        session_id=session_id,
        student_id=student_id,
        mark="present",
        marked_at=marked_at,
        actor_user_id=actor_id,
    )

    assert event.event_id == uuid.uuid5(uuid.NAMESPACE_URL, f"verity-attendance:{event_id}")
    assert event.payload == {
        "event_id": str(event.event_id),
        "source_event_id": event_id,
        "session_id": str(session_id),
        "student_id": str(student_id),
        "mark": "present",
        "marked_at": marked_at.isoformat(),
        "actor_user_id": str(actor_id),
    }
    assert not {"image", "embedding"}.intersection(event.payload)
    db.add.assert_called_once_with(event)
    second = enqueue_attendance_event(
        Mock(),
        source_event_id=event_id,
        session_id=session_id,
        student_id=student_id,
        mark="present",
        marked_at=marked_at,
        actor_user_id=actor_id,
    )
    assert second.event_id == event.event_id


def test_offline_network_failure_keeps_event_pending_for_recovery() -> None:
    event = SimpleNamespace(
        event_id=uuid.uuid4(),
        payload={"event_id": "event"},
        attempt_count=0,
        last_attempt_at=None,
        status="pending",
        last_error=None,
        synced_at=None,
    )
    scalar_result = Mock()
    scalar_result.all.return_value = [event]
    db = AsyncMock()
    db.scalars.return_value = scalar_result
    async def exercise() -> dict[str, int]:
        with patch.dict(
            "os.environ",
            {
                "VERITY_SYNC_URL": "http://127.0.0.1:9000",
                "VERITY_SYNC_TOKEN": "local-test-token",
            },
        ), patch("app.services.attendance_outbox.urlopen", side_effect=URLError("offline")):
            return await sync_pending_outbox(db)

    first = asyncio.run(exercise())
    assert first == {"sent": 0, "conflicts": 0, "retrying": 1}
    assert event.status == "pending"
    assert event.attempt_count == 1
    assert event.last_error == "network_unavailable"
    db.commit.assert_awaited_once()


def test_pending_event_syncs_after_connectivity_recovers() -> None:
    event = SimpleNamespace(
        event_id=uuid.uuid4(),
        payload={"event_id": "event"},
        attempt_count=0,
        last_attempt_at=None,
        status="pending",
        last_error="network_unavailable",
        synced_at=None,
    )
    scalar_result = Mock()
    scalar_result.all.return_value = [event]
    db = AsyncMock()
    db.scalars.return_value = scalar_result
    response = Mock(status=201)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    async def exercise() -> dict[str, int]:
        with patch.dict(
            "os.environ",
            {
                "VERITY_SYNC_URL": "https://attendance.example.edu",
                "VERITY_SYNC_TOKEN": "local-test-token",
            },
        ), patch("app.services.attendance_outbox.urlopen", return_value=response) as send:
            result = await sync_pending_outbox(db)
            assert result == {"sent": 1, "conflicts": 0, "retrying": 0}
            assert event.status == "synced"
            assert event.synced_at is not None
            send.assert_called_once()
            request = send.call_args.args[0]
            assert request.full_url == "https://attendance.example.edu/api/v1/sync/attendance"
            assert request.get_header("Idempotency-key") == str(event.event_id)
            return result

    asyncio.run(exercise())


def test_sync_conflict_is_persisted_for_manual_resolution() -> None:
    event = SimpleNamespace(
        event_id=uuid.uuid4(),
        payload={"event_id": "event"},
        attempt_count=0,
        last_attempt_at=None,
        status="pending",
        last_error=None,
        synced_at=None,
    )
    scalar_result = Mock()
    scalar_result.all.return_value = [event]
    db = AsyncMock()
    db.scalars.return_value = scalar_result

    async def exercise() -> dict[str, int]:
        with patch.dict(
            "os.environ",
            {
                "VERITY_SYNC_URL": "https://attendance.example.edu",
                "VERITY_SYNC_TOKEN": "local-test-token",
            },
        ), patch(
            "app.services.attendance_outbox.urlopen",
            side_effect=HTTPError("https://attendance.example.edu", 409, "conflict", {}, None),
        ):
            return await sync_pending_outbox(db)

    assert asyncio.run(exercise()) == {"sent": 0, "conflicts": 1, "retrying": 0}
    assert event.status == "conflict"
    assert event.last_error == "http_409"


def test_database_commit_failure_is_not_reported_as_a_success() -> None:
    db = AsyncMock()
    db.scalars.return_value = Mock(all=Mock(return_value=[]))
    db.commit.side_effect = SQLAlchemyError("database unavailable")

    async def exercise() -> dict[str, int]:
        with patch.dict(
            "os.environ",
            {
                "VERITY_SYNC_URL": "https://attendance.example.edu",
                "VERITY_SYNC_TOKEN": "local-test-token",
            },
        ):
            return await sync_pending_outbox(db)

    with pytest.raises(SQLAlchemyError, match="database unavailable"):
        asyncio.run(exercise())


def test_sync_payload_validates_idempotency_and_timezone() -> None:
    source_event_id = _source_event_id()
    expected = uuid.uuid5(uuid.NAMESPACE_URL, f"verity-attendance:{source_event_id}")
    payload = AttendanceSyncInput(
        event_id=expected,
        source_event_id=source_event_id,
        session_id=uuid.uuid4(),
        student_id=uuid.uuid4(),
        mark="present",
        marked_at=datetime.now(UTC),
    )
    assert payload.event_id == expected
    correction_id = _source_event_id()
    correction_payload = AttendanceSyncInput(
        event_id=uuid.uuid5(uuid.NAMESPACE_URL, f"verity-attendance:{correction_id}"),
        source_event_id=correction_id,
        session_id=uuid.uuid4(),
        student_id=uuid.uuid4(),
        mark="late",
        marked_at=datetime.now(UTC),
        correction=True,
        correction_of=source_event_id,
        correction_reason="Lecturer verified roster evidence.",
    )
    assert correction_payload.correction
    with pytest.raises(ValidationError, match="must include a reason"):
        AttendanceSyncInput(
            event_id=uuid.uuid5(uuid.NAMESPACE_URL, f"verity-attendance:{correction_id}"),
            source_event_id=correction_id,
            session_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            mark="late",
            marked_at=datetime.now(UTC),
            correction=True,
        )
    with pytest.raises(ValidationError, match="does not match"):
        AttendanceSyncInput(
            event_id=uuid.uuid4(),
            source_event_id=source_event_id,
            session_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            mark="present",
            marked_at=datetime.now(UTC),
        )


def test_sync_receiver_requires_shared_token() -> None:
    with patch.dict("os.environ", {"VERITY_SYNC_TOKEN": "expected"}):
        with pytest.raises(HTTPException) as caught:
            _authorized_sync_request("Bearer wrong")
        assert caught.value.status_code == 401
        _authorized_sync_request("Bearer expected")
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as caught:
            _authorized_sync_request(None)
        assert caught.value.status_code == 503
