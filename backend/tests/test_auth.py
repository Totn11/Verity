from __future__ import annotations

import asyncio
import json
import os
import uuid
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.auth.audit import LOGIN_FAILURE_ACTION, count_recent_login_failures
from app.auth.passwords import hash_password, verify_password, verify_unknown_user_password
from app.auth.tokens import encode_token, get_token_keyset, issue_claims, verify_token
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
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = Ed25519PrivateKey.generate()
        private_pem = cls.private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        public_pem = cls.private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        cls.jwt_environment = patch.dict(
            os.environ,
            {
                "VERITY_JWT_SIGNING_KID": "test-key",
                "VERITY_JWT_PRIVATE_KEY": private_pem,
                "VERITY_JWT_PUBLIC_KEYS": json.dumps({"test-key": public_pem}),
                "VERITY_JWT_AUDIENCE": "https://verity.example",
            },
        )
        cls.jwt_environment.start()
        get_token_keyset.cache_clear()

    @classmethod
    def tearDownClass(cls) -> None:
        get_token_keyset.cache_clear()
        cls.jwt_environment.stop()

    @staticmethod
    def make_user(*, role: str = "admin", session_version: int = 0) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid.uuid4(),
            role=role,
            session_version=session_version,
            is_active=True,
        )

    @classmethod
    def make_token(
        cls,
        user: SimpleNamespace | None = None,
        *,
        session_id: uuid.UUID | None = None,
    ) -> tuple[str, SimpleNamespace, uuid.UUID]:
        user = user or cls.make_user()
        session_id = session_id or uuid.uuid4()
        return encode_token(issue_claims(user, session_id)), user, session_id

    def test_create_session_stores_only_hash_and_sets_secure_cookie(self) -> None:
        user = self.make_user()
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
        self.assertIn(f"{COOKIE_NAME.lower()}=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("path=/", cookie)
        self.assertTrue(token.count(".") == 2)
        self.assertEqual(stored_session.id, uuid.UUID(verify_token(token)["sid"]))

    def test_read_session_rejects_revoked_session(self) -> None:
        token, user, session_id = self.make_token()
        now = datetime.now(UTC)
        session = SimpleNamespace(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(token),
            revoked_at=now,
            expires_at=now + timedelta(hours=1),
            user=user,
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        returned_user = asyncio.run(read_session(make_request(cookie=token), db))

        self.assertIsNone(returned_user)
        statement = db.execute.await_args.args[0]
        rendered_query = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("sessions.revoked_at IS NULL", rendered_query)
        self.assertIn("sessions.expires_at >", rendered_query)

    def test_read_session_accepts_valid_session(self) -> None:
        token, user, session_id = self.make_token()
        now = datetime.now(UTC)
        session = SimpleNamespace(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(token),
            revoked_at=None,
            expires_at=now + timedelta(hours=1),
            user=user,
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        self.assertIs(asyncio.run(read_session(make_request(cookie=token), db)), user)

    def test_read_session_rejects_stale_session_version(self) -> None:
        token, user, session_id = self.make_token()
        user.session_version += 1
        session = SimpleNamespace(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(token),
            revoked_at=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user=user,
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        self.assertIsNone(asyncio.run(read_session(make_request(cookie=token), db)))

    def test_revoke_session_sets_revoked_at(self) -> None:
        token, user, session_id = self.make_token()
        session = SimpleNamespace(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(token),
            revoked_at=None,
        )
        result = Mock()
        result.scalar_one_or_none.return_value = session
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        revoked = asyncio.run(revoke_session(make_request(cookie=token), db))

        self.assertTrue(revoked)
        self.assertIsNotNone(session.revoked_at)

    def test_jwt_rejects_unsafe_or_invalid_claims(self) -> None:
        user = self.make_user()
        claims = issue_claims(user, uuid.uuid4())
        invalid_tokens = [
            jwt.encode(claims, "", algorithm="none", headers={"kid": "test-key"}),
            jwt.encode(
                {**claims, "aud": "https://other.example"},
                self.private_key,
                algorithm="EdDSA",
                headers={"kid": "test-key"},
            ),
            jwt.encode(
                {**claims, "exp": int(datetime.now(UTC).timestamp()) - 60},
                self.private_key,
                algorithm="EdDSA",
                headers={"kid": "test-key"},
            ),
            jwt.encode(
                claims,
                self.private_key,
                algorithm="EdDSA",
                headers={"kid": "unknown-key"},
            ),
        ]

        for token in invalid_tokens:
            with self.subTest(token_header=jwt.get_unverified_header(token)):
                with self.assertRaises(jwt.InvalidTokenError):
                    verify_token(token)

    def test_role_and_password_changes_bump_session_version(self) -> None:
        from sqlalchemy import inspect

        from app.db.models import User, UserRole

        for attribute, value in (
            ("role", UserRole.STAFF),
            ("password_hash", "updated-hash"),
        ):
            with self.subTest(attribute=attribute):
                user = User(
                    id=uuid.uuid4(),
                    email=f"{attribute}@example.com",
                    password_hash="initial-hash",
                    display_name="Test User",
                    role=UserRole.ADMIN,
                    session_version=4,
                )
                setattr(user, attribute, value)

                User.__mapper__.dispatch.before_update(
                    User.__mapper__,
                    None,
                    inspect(user),
                )

                self.assertEqual(user.session_version, 5)

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
        body = response.json()
        self.assertEqual(
            {key: body[key] for key in ("authenticated", "email", "user_id", "role")},
            {
                "authenticated": True,
                "email": user.email,
                "user_id": str(user.id),
                "role": "admin",
            },
        )
        self.assertIsInstance(body["expires_at"], int)
        self.assertIsNotNone(user.last_login_at)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Domain=", cookie)
        stored_session = next(item for item in added if isinstance(item, UserSession))
        audit_event = next(item for item in added if isinstance(item, AuditEvent))
        cookie_token = cookie.split("=", maxsplit=1)[1].split(";", maxsplit=1)[0]
        self.assertNotIn(cookie_token, stored_session.token_hash)
        self.assertEqual(audit_event.action, "auth.login")

    def test_me_returns_verified_identity_claims_without_exposing_cookie(self) -> None:
        from app.db.models import User, UserRole
        from app.db.session import get_session
        from app.main import app

        user = User(
            id=uuid.uuid4(),
            email="operator@example.com",
            password_hash=hash_password("valid-password-123"),
            display_name="Operator",
            role=UserRole.ADMIN,
            is_active=True,
            session_version=0,
        )
        session_id = uuid.uuid4()
        claims = issue_claims(user, session_id)
        token = encode_token(claims)
        row = SimpleNamespace(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(token),
            revoked_at=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user=user,
        )
        result = Mock()
        result.scalar_one_or_none.return_value = row
        db = Mock()
        db.execute = AsyncMock(return_value=result)

        async def override_get_session():
            yield db

        app.dependency_overrides[get_session] = override_get_session
        try:
            response = TestClient(app).get(
                "/api/auth/me",
                headers={"Cookie": f"{COOKIE_NAME}={token}"},
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "authenticated": True,
                "email": user.email,
                "user_id": str(user.id),
                "role": "admin",
                "expires_at": claims["exp"],
            },
        )
        self.assertNotIn(token, response.text)

    def test_logout_revokes_session_and_clears_cookie(self) -> None:
        from app.db.session import get_session
        from app.main import app

        token, user, session_id = self.make_token()
        session = SimpleNamespace(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(token),
            revoked_at=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user=user,
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
                headers={"Cookie": f"{COOKIE_NAME}={token}"},
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
        ("academic reads", {"admin", "staff", "lecturer"}),
        ("academic writes", {"admin"}),
        ("attendance writes", {"admin", "staff", "lecturer"}),
    ],
)
@pytest.mark.parametrize("role", [None, "admin", "staff", "lecturer", "visitor"])
def test_authorization_matrix_at_router_boundary(
    router_name: str,
    allowed_roles: set[str],
    role: str | None,
) -> None:
    from app.db.session import get_session
    from app.api.v1.academic import attendance_access, read_access, write_access

    access_dependency = {
        "academic reads": read_access,
        "academic writes": write_access,
        "attendance writes": attendance_access,
    }[router_name]
    test_router = APIRouter(
        prefix="/academic",
        dependencies=[Depends(access_dependency)],
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
        response = TestClient(test_app).get("/academic/authorization-probe")

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
