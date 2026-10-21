from __future__ import annotations

import asyncio
import uuid
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.auth.audit import LOGIN_FAILURE_ACTION, count_recent_login_failures
from app.auth.passwords import hash_password, verify_password, verify_unknown_user_password
from app.auth.sessions import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_session,
    hash_ip,
    hash_token,
    read_session,
    revoke_session,
)


def make_request(
    *,
    cookie: str | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    request_headers = headers or []
    if cookie:
        request_headers.append((b"cookie", f"{COOKIE_NAME}={cookie}".encode()))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/auth/login",
            "raw_path": b"/api/auth/login",
            "query_string": b"",
            "headers": request_headers,
            "client": ("203.0.113.12", 12345),
            "server": ("testserver", 443),
        }
    )


class PasswordTests(unittest.TestCase):
    def test_argon2_hashes_verify_and_reject_wrong_password(self) -> None:
        password_hash = hash_password("correct horse battery staple")

        self.assertTrue(password_hash.startswith("$argon2"))
        self.assertTrue(verify_password(password_hash, "correct horse battery staple"))
        self.assertFalse(verify_password(password_hash, "wrong password"))
        self.assertFalse(verify_password("not-an-argon2-hash", "wrong password"))

    def test_unknown_user_path_runs_dummy_password_verification(self) -> None:
        verify_unknown_user_password("any submitted password")


class SessionTests(unittest.TestCase):
    def test_create_session_stores_only_hash_and_sets_secure_cookie(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        request = make_request(headers=[(b"user-agent", b"test-agent")])
        response = Response()
        db = Mock()
        db.add = Mock()

        token = asyncio.run(create_session(user, request, response, db))

        stored_session = db.add.call_args.args[0]
        self.assertNotEqual(token, stored_session.token_hash)
        self.assertEqual(stored_session.token_hash, hash_token(token))
        self.assertEqual(stored_session.user_agent, "test-agent")
        self.assertEqual(stored_session.ip_hash, hash_ip(request))
        self.assertEqual(
            stored_session.expires_at - stored_session.issued_at,
            timedelta(seconds=SESSION_TTL_SECONDS),
        )
        cookie = response.headers["set-cookie"].lower()
        self.assertIn(f"{COOKIE_NAME}=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=lax", cookie)

    def test_read_session_rejects_revoked_session(self) -> None:
        now = datetime.now(UTC)
        session = SimpleNamespace(
            revoked_at=now,
            expires_at=now + timedelta(hours=1),
            user=SimpleNamespace(is_active=True),
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        user = asyncio.run(read_session(make_request(cookie="opaque-cookie-token"), db))

        self.assertIsNone(user)
        statement = db.execute.await_args.args[0]
        rendered_query = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("sessions.revoked_at IS NULL", rendered_query)
        self.assertIn("sessions.expires_at >", rendered_query)

    def test_read_session_accepts_valid_session(self) -> None:
        now = datetime.now(UTC)
        user = SimpleNamespace(is_active=True)
        session = SimpleNamespace(
            revoked_at=None,
            expires_at=now + timedelta(hours=1),
            user=user,
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        self.assertIs(asyncio.run(read_session(make_request(cookie="opaque-cookie-token"), db)), user)

    def test_revoke_session_sets_revoked_at(self) -> None:
        session = SimpleNamespace(revoked_at=None)
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        revoked = asyncio.run(revoke_session(make_request(cookie="opaque-cookie-token"), db))

        self.assertTrue(revoked)
        self.assertIsNotNone(session.revoked_at)

    def test_rate_limit_counts_failures_for_hashed_ip_since_cutoff(self) -> None:
        request = make_request()
        cutoff = datetime.now(UTC) - timedelta(minutes=15)
        result = Mock()
        result.scalar_one.return_value = 4
        db = Mock()
        db.execute = AsyncMock(side_effect=[Mock(), result])

        failures = asyncio.run(count_recent_login_failures(request, db, since=cutoff))

        self.assertEqual(failures, 4)
        query, parameters = db.execute.await_args_list[0].args
        self.assertIn("pg_advisory_xact_lock", str(query))
        count_query = db.execute.await_args_list[1].args[0]
        rendered_query = str(count_query.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn(LOGIN_FAILURE_ACTION, rendered_query)
        self.assertIn(hash_ip(request), rendered_query)
        self.assertIn("created_at >=", rendered_query)
        self.assertIsInstance(parameters["lock_id"], int)

    def test_login_uses_generic_errors_for_unknown_and_wrong_password(self) -> None:
        from app.db.models import User, UserRole
        from app.db.session import get_session
        from app.main import app

        valid_user = User(
            id=uuid.uuid4(),
            email="operator@example.com",
            password_hash=hash_password("valid-password-123"),
            display_name="Operator",
            role=UserRole.ADMIN,
            is_active=True,
        )
        bodies: list[dict[str, str]] = []
        for db_user, submitted_password in (
            (None, "valid-password-123"),
            (valid_user, "wrong-password"),
        ):
            db = Mock()
            count_result = Mock()
            count_result.scalar_one.return_value = 0
            user_result = Mock()
            user_result.scalar_one_or_none.return_value = db_user
            db.execute = AsyncMock(side_effect=[Mock(), count_result, user_result])
            db.add = Mock()
            db.flush = AsyncMock()
            db.commit = AsyncMock()

            async def override_get_session():
                yield db

            app.dependency_overrides[get_session] = override_get_session
            try:
                response = TestClient(app).post(
                    "/api/auth/login",
                    json={"email": "operator@example.com", "password": submitted_password},
                )
            finally:
                app.dependency_overrides.clear()
            bodies.append(response.json())
            self.assertEqual(response.status_code, 401)

        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(bodies[0], {"detail": "Email or password is incorrect."})

    def test_login_rate_limit_returns_429_after_five_failures(self) -> None:
        from app.db.session import get_session
        from app.main import app

        db = Mock()
        failure_count = Mock()
        failure_count.scalar_one.return_value = 5
        db.execute = AsyncMock(side_effect=[Mock(), failure_count])

        async def override_get_session():
            yield db

        app.dependency_overrides[get_session] = override_get_session
        try:
            response = TestClient(app).post(
                "/api/auth/login",
                json={"email": "operator@example.com", "password": "wrong-password"},
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json(),
            {"detail": "Too many sign-in attempts. Try again later."},
        )

    def test_successful_login_updates_user_and_audits_without_storing_token(self) -> None:
        from app.db.models import AuditEvent, Session as UserSession, User, UserRole
        from app.db.session import get_session
        from app.main import app

        user = User(
            id=uuid.uuid4(),
            email="operator@example.com",
            password_hash=hash_password("valid-password-123"),
            display_name="Operator",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db = Mock()
        count_result = Mock()
        count_result.scalar_one.return_value = 0
        user_result = Mock()
        user_result.scalar_one_or_none.return_value = user
        added: list[object] = []
        db.execute = AsyncMock(side_effect=[Mock(), count_result, user_result])
        db.add.side_effect = added.append
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        async def override_get_session():
            yield db

        app.dependency_overrides[get_session] = override_get_session
        try:
            response = TestClient(app).post(
                "/api/auth/login",
                json={"email": "operator@example.com", "password": "valid-password-123"},
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"authenticated": True, "email": user.email})
        self.assertIsNotNone(user.last_login_at)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        stored_session = next(item for item in added if isinstance(item, UserSession))
        audit_event = next(item for item in added if isinstance(item, AuditEvent))
        cookie_token = cookie.split("=", maxsplit=1)[1].split(";", maxsplit=1)[0]
        self.assertNotIn(cookie_token, stored_session.token_hash)
        self.assertEqual(audit_event.action, "auth.login")

    def test_logout_revokes_session_and_clears_cookie(self) -> None:
        from app.db.session import get_session
        from app.main import app

        session = SimpleNamespace(
            revoked_at=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user=SimpleNamespace(id=uuid.uuid4(), is_active=True),
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)
        db.add = Mock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        async def override_get_session():
            yield db

        app.dependency_overrides[get_session] = override_get_session
        try:
            response = TestClient(app).post(
                "/api/auth/logout",
                headers={"Cookie": f"{COOKIE_NAME}=opaque-cookie-token"},
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(session.revoked_at)
        db.commit.assert_awaited_once()
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        audit_event = db.add.call_args.args[0]
        self.assertEqual(audit_event.action, "auth.logout")
        self.assertEqual(audit_event.request_id, response.headers["x-request-id"])


@pytest.mark.parametrize(
    ("router_name", "allowed_roles"),
    [
        ("people reads", {"admin", "staff"}),
        ("people writes", {"admin"}),
        ("rooms reads", {"admin", "staff"}),
        ("rooms writes", {"admin"}),
        ("attendance reads", {"admin", "staff"}),
        ("reports reads", {"admin", "staff"}),
        ("role management", {"admin"}),
        ("audit-log viewing", {"admin"}),
        ("user management", {"admin"}),
    ],
)
@pytest.mark.parametrize("role", [None, "admin", "staff", "visitor"])
def test_authorization_matrix_at_router_boundary(
    router_name: str,
    allowed_roles: set[str],
    role: str | None,
) -> None:
    from app.db.session import get_session
    from app.main import AUTHORIZATION_ROUTERS

    protected_router = AUTHORIZATION_ROUTERS[router_name]
    test_router = APIRouter(
        prefix=protected_router.prefix,
        dependencies=protected_router.dependencies,
    )
    test_router.add_api_route(
        "/authorization-probe",
        lambda: {"authorized": True},
        methods=["GET"],
    )
    test_app = FastAPI()
    test_app.include_router(test_router)

    async def override_get_session():
        yield Mock()

    test_app.dependency_overrides[get_session] = override_get_session
    user = SimpleNamespace(role=role) if role is not None else None

    with patch(
        "app.auth.dependencies.read_session",
        new_callable=AsyncMock,
        return_value=user,
    ):
        response = TestClient(test_app).get(
            f"{protected_router.prefix}/authorization-probe"
        )

    expected_status = (
        401
        if role is None
        else 200
        if role in allowed_roles
        else 403
    )
    assert response.status_code == expected_status


if __name__ == "__main__":
    unittest.main()
