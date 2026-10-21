from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.memory import InMemoryAuditRepository
from app.services.audit import AuditService


def test_audit_service_records_actor_request_and_before_after() -> None:
    async def exercise() -> None:
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "PATCH",
                "scheme": "https",
                "path": "/api/v1/people/example",
                "raw_path": b"/api/v1/people/example",
                "query_string": b"",
                "headers": [],
                "client": ("203.0.113.10", 12345),
                "server": ("testserver", 443),
                "state": {"request_id": str(uuid.uuid4())},
            }
        )
        actor = SimpleNamespace(id=uuid.uuid4())
        repository = InMemoryAuditRepository()

        event = await AuditService(request, repository).record(
            actor,
            "people.update",
            "person",
            "person-123",
            {"title": "Analyst"},
            {"title": "Engineer"},
        )

        assert event.actor_user_id == actor.id
        assert event.request_id == request.state.request_id
        assert event.action == "people.update"
        assert event.entity_type == "person"
        assert event.entity_id == "person-123"
        assert event.before == {"title": "Analyst"}
        assert event.after == {"title": "Engineer"}
        assert len(await repository.list()) == 1

    asyncio.run(exercise())


def test_response_echoes_generated_request_id() -> None:
    response = TestClient(app).get("/api/health")
    request_id = response.headers["x-request-id"]
    parsed_id = uuid.UUID(request_id)
    assert str(parsed_id) == request_id
    assert parsed_id.version == 4


def test_append_only_migration_defines_update_and_delete_trigger() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20261021_0002_audit_events_append_only.py"
    ).read_text()
    assert "BEFORE UPDATE OR DELETE ON audit_events" in migration
    assert "RAISE EXCEPTION 'audit_events is append-only'" in migration


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to a migrated PostgreSQL test database.",
)
def test_postgres_refuses_audit_event_updates_and_deletes() -> None:
    async def exercise() -> None:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection:
                async with connection.begin():
                    result = await connection.execute(
                        text(
                            """
                            INSERT INTO audit_events
                                (actor_user_id, action, entity_type, entity_id,
                                 before, after, request_id, ip_hash)
                            VALUES
                                (NULL, 'test.append_only', 'test', :entity_id,
                                 '{}'::jsonb, '{}'::jsonb, :request_id, 'test')
                            RETURNING id
                            """
                        ),
                        {
                            "entity_id": str(uuid.uuid4()),
                            "request_id": str(uuid.uuid4()),
                        },
                    )
                    event_id = result.scalar_one()
                    for statement in (
                        "UPDATE audit_events SET action = 'changed' WHERE id = :event_id",
                        "DELETE FROM audit_events WHERE id = :event_id",
                    ):
                        with pytest.raises(DBAPIError):
                            async with connection.begin_nested():
                                await connection.execute(
                                    text(statement), {"event_id": event_id}
                                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
