from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_user
from app.db.models import Person, PersonStatus, Room
from app.main import app
from app.repositories.dependencies import RepositorySet, get_repositories
from app.repositories.memory import (
    InMemoryAttendanceRepository,
    InMemoryAuditRepository,
    InMemoryPeopleRepository,
    InMemoryRoomsRepository,
)


@pytest.fixture
def api_client():
    repositories = RepositorySet(
        people=InMemoryPeopleRepository(),
        rooms=InMemoryRoomsRepository(),
        attendance=InMemoryAttendanceRepository(),
        audit=InMemoryAuditRepository(),
    )
    user = SimpleNamespace(id=uuid.uuid4(), role="admin")

    async def override_user():
        return user

    async def override_repositories():
        yield repositories

    app.dependency_overrides[require_user] = override_user
    app.dependency_overrides[get_repositories] = override_repositories
    with TestClient(app) as client:
        yield client, repositories, user
    app.dependency_overrides.clear()


def create_person(name: str, *, status: PersonStatus = PersonStatus.ACTIVE) -> Person:
    return Person(
        external_ref=f"ref-{name}",
        full_name=name,
        email=f"{name.lower()}@example.com",
        phone="555-0100",
        department="Operations",
        title="Staff",
        status=status,
    )


@pytest.mark.parametrize(
    ("role", "method", "path", "expected_status"),
    [
        ("staff", "GET", "/api/v1/people", 200),
        ("staff", "POST", "/api/v1/people", 403),
        ("staff", "PATCH", f"/api/v1/people/{uuid.uuid4()}", 403),
        ("staff", "GET", "/api/v1/rooms", 200),
        ("staff", "GET", "/api/v1/attendance", 200),
        ("staff", "POST", "/api/v1/attendance/check-in", 201),
        ("staff", "GET", "/api/v1/reports/attendance-summary", 200),
    ],
)
def test_v1_router_enforces_server_authorization(
    api_client, role: str, method: str, path: str, expected_status: int
) -> None:
    client, repositories, user = api_client
    user.role = role
    payload = {
        "external_ref": "new-person",
        "full_name": "New Person",
        "email": "new@example.com",
        "phone": "555-0101",
        "department": "Operations",
        "title": "Staff",
        "status": "active",
    }
    if path.endswith("/check-in"):
        person = asyncio.run(
            repositories.people.create(create_person("Attendance Person"))
        )
        payload = {"person_id": str(person.id)}
    if method == "GET":
        response = client.get(path)
    elif method == "POST":
        response = client.post(path, json=payload)
    else:
        response = client.patch(path, json={"title": "Manager"})
    assert response.status_code == expected_status, response.text


def test_people_search_filter_and_cursor_pagination(api_client) -> None:
    client, repositories, _ = api_client
    asyncio.run(repositories.people.create(create_person("Ada Lovelace")))
    asyncio.run(repositories.people.create(create_person("Ada Byron")))
    asyncio.run(
        repositories.people.create(
            create_person("Grace Hopper", status=PersonStatus.INACTIVE)
        )
    )

    first_page = client.get(
        "/api/v1/people",
        params={"q": "Ada", "status": "active", "limit": 1},
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 1
    assert first_body["items"][0]["full_name"] == "Ada Byron"
    assert first_body["next_cursor"]

    second_page = client.get(
        "/api/v1/people",
        params={
            "q": "Ada",
            "status": "active",
            "limit": 1,
            "cursor": first_body["next_cursor"],
        },
    )
    assert [item["full_name"] for item in second_page.json()["items"]] == [
        "Ada Lovelace"
    ]
    assert second_page.json()["next_cursor"] is None


def test_people_create_update_and_room_listing(api_client) -> None:
    client, repositories, _ = api_client
    payload = {
        "external_ref": "person-1",
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "555-0100",
        "department": "Research",
        "title": "Engineer",
        "status": "active",
    }
    created = client.post("/api/v1/people", json=payload)
    assert created.status_code == 201, created.text
    person_id = created.json()["id"]
    updated = client.patch(
        f"/api/v1/people/{person_id}",
        json={"title": "Principal Engineer", "photo_url": None},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Principal Engineer"
    assert updated.json()["photo_url"] is None
    assert client.get(f"/api/v1/people/{person_id}").status_code == 200
    audit_events = asyncio.run(repositories.audit.list())
    assert [event.action for event in audit_events] == [
        "people.update",
        "people.create",
    ]
    assert audit_events[0].before["title"] == "Engineer"
    assert audit_events[0].after["title"] == "Principal Engineer"
    assert audit_events[0].request_id == updated.headers["x-request-id"]

    room = Room(
        code="A-101",
        name="Meeting Room",
        floor=1,
        capacity=8,
        pos_x=Decimal("1"),
        pos_y=Decimal("2"),
    )
    room = asyncio.run(repositories.rooms.create(room))
    response = client.get("/api/v1/rooms", params={"limit": 1})
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(room.id)
    assert client.get(f"/api/v1/rooms/{room.id}").json()["code"] == "A-101"


def test_attendance_idempotency_filter_and_summary(api_client) -> None:
    client, repositories, _ = api_client
    person = asyncio.run(repositories.people.create(create_person("Visitor")))
    room = asyncio.run(
        repositories.rooms.create(
            Room(
                code="B-202",
                name="Conference",
                floor=2,
                capacity=12,
                pos_x=Decimal("3"),
                pos_y=Decimal("4"),
            )
        )
    )
    event_time = "2026-10-20T10:00:00-04:00"
    first = client.post(
        "/api/v1/attendance/check-in",
        json={
            "person_id": str(person.id),
            "room_id": str(room.id),
            "occurred_at": event_time,
        },
        headers={"Idempotency-Key": "terminal-event-1"},
    )
    replay = client.post(
        "/api/v1/attendance/check-in",
        json={
            "person_id": str(person.id),
            "room_id": str(room.id),
            "occurred_at": event_time,
        },
        headers={"Idempotency-Key": "terminal-event-1"},
    )
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["occurred_at"] == "2026-10-20T14:00:00Z"
    audit_events = asyncio.run(repositories.audit.list())
    assert [event.action for event in audit_events] == ["attendance.check_in"] * 2
    assert audit_events[0].after["id"] == first.json()["id"]
    assert first.headers["x-request-id"] in {
        event.request_id for event in audit_events
    }

    listing = client.get(
        "/api/v1/attendance",
        params={
            "person_id": str(person.id),
            "from": "2026-10-20T13:00:00Z",
            "to": "2026-10-20T15:00:00Z",
        },
    )
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    check_out = client.post(
        "/api/v1/attendance/check-out",
        json={
            "person_id": str(person.id),
            "room_id": str(room.id),
            "occurred_at": "2026-10-20T15:00:00Z",
        },
    )
    assert check_out.status_code == 201
    summary = client.get(
        "/api/v1/reports/attendance-summary",
        params={"from": "2026-10-20T00:00:00Z", "to": "2026-10-21T00:00:00Z"},
    )
    assert summary.status_code == 200
    assert summary.json()["items"] == [
        {
            "day": "2026-10-20T00:00:00Z",
            "room_id": str(room.id),
            "room_code": "B-202",
            "room_name": "Conference",
            "check_ins": 1,
            "check_outs": 1,
        }
    ]


@pytest.mark.parametrize(
    ("path", "method", "payload"),
    [
        (
            "/api/v1/attendance/check-in",
            "POST",
            {"person_id": str(uuid.uuid4()), "occurred_at": "2026-10-20T10:00:00"},
        ),
        (
            "/api/v1/attendance?from=2026-10-20T10:00:00",
            "GET",
            None,
        ),
        (
            "/api/v1/reports/attendance-summary?to=2026-10-20T10:00:00",
            "GET",
            None,
        ),
    ],
)
def test_naive_timestamps_are_rejected(api_client, path, method, payload) -> None:
    client, _, _ = api_client
    response = (
        client.post(path, json=payload)
        if method == "POST"
        else client.get(path)
    )
    assert response.status_code == 422


def test_invalid_cursor_and_invalid_date_range_are_rejected(api_client) -> None:
    client, _, _ = api_client
    assert client.get("/api/v1/people", params={"cursor": "not-a-cursor"}).status_code == 422
    assert (
        client.get(
            "/api/v1/attendance",
            params={
                "from": "2026-10-21T00:00:00Z",
                "to": "2026-10-20T00:00:00Z",
            },
        ).status_code
        == 422
    )
