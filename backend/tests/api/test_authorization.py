"""Authorization tests for protected endpoints.

The Supabase client is stubbed at the dependency boundary so the tests
exercise token verification, identity derivation and route protection
without network access. Repository behaviour is covered separately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context
from app.core.config import get_settings
from app.main import create_app

SECRET = "test-jwt-secret-with-at-least-32-characters-long"
USER_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with Supabase configuration present but no network client."""
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijklm.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-anon")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    get_settings.cache_clear()

    application = create_app()
    yield TestClient(application)
    get_settings.cache_clear()


def make_token(sub: str = USER_ID, exp_delta: int = 3600) -> str:
    return jwt.encode(
        {
            "sub": sub,
            "email": "alice@mnemos.test",
            "role": "authenticated",
            "exp": datetime.now(UTC) + timedelta(seconds=exp_delta),
        },
        SECRET,
        algorithm="HS256",
    )


PROTECTED_ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/v1/me"),
    ("PATCH", "/api/v1/me"),
    ("GET", "/api/v1/me/preferences"),
    ("PUT", "/api/v1/me/preferences"),
    ("GET", "/api/v1/workspaces"),
    ("POST", "/api/v1/workspaces"),
    ("GET", "/api/v1/workspaces/abc"),
    ("PATCH", "/api/v1/workspaces/abc"),
    ("DELETE", "/api/v1/workspaces/abc"),
    ("GET", "/api/v1/workspaces/abc/members"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
def test_requires_authentication(client: TestClient, method: str, path: str) -> None:
    """Every protected route rejects anonymous callers with the envelope."""
    response = client.request(method, path, json={} if method in {"POST", "PATCH", "PUT"} else None)
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"]


@pytest.mark.parametrize(
    "header",
    [
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer    ",
        "token-without-scheme",
        "",
    ],
)
def test_malformed_authorization_header(client: TestClient, header: str) -> None:
    response = client.get("/api/v1/me", headers={"Authorization": header})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_expired_token_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {make_token(exp_delta=-60)}"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


def test_forged_token_rejected(client: TestClient) -> None:
    forged = jwt.encode(
        {"sub": USER_ID, "exp": datetime.now(UTC) + timedelta(hours=1)},
        "attacker-secret-value-that-is-long-enough",
        algorithm="HS256",
    )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_valid_token_reaches_handler(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A verified token yields an identity derived from the token subject."""
    captured: dict[str, Any] = {}

    def fake_context() -> Any:
        from app.api.deps import AuthContext
        from app.domain.identity import Identity

        identity = Identity(user_id=USER_ID, email="alice@mnemos.test", role="authenticated")
        captured["identity"] = identity
        raise_for = getattr(fake_context, "stub", None)
        if raise_for:
            raise raise_for
        from fastapi import HTTPException

        raise HTTPException(status_code=418, detail="reached handler")

    # The dependency itself is what we verify here: identity comes from token.
    client.app.dependency_overrides[get_auth_context] = fake_context  # type: ignore[attr-defined]
    try:
        response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {make_token()}"})
        assert response.status_code == 418
        assert captured["identity"].user_id == USER_ID
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def test_health_remains_public(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ready").status_code == 200


def test_openapi_lists_protected_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/me" in paths
    assert "/api/v1/workspaces" in paths
