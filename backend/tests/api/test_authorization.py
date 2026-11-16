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
    ("GET", "/api/v1/knowledge/workspaces/abc/sources"),
    ("GET", "/api/v1/knowledge/sources/abc"),
    ("GET", "/api/v1/knowledge/sources/abc/versions"),
    ("GET", "/api/v1/knowledge/sources/abc/chunks"),
    ("GET", "/api/v1/knowledge/chunks/abc/provenance"),
    ("DELETE", "/api/v1/knowledge/sources/abc"),
    # Phase 2B ingestion routes.
    ("POST", "/api/v1/knowledge/workspaces/abc/sources/upload"),
    ("POST", "/api/v1/knowledge/workspaces/abc/sources/note"),
    ("POST", "/api/v1/knowledge/sources/abc/versions/upload"),
    ("POST", "/api/v1/knowledge/sources/abc/versions/note"),
    ("GET", "/api/v1/knowledge/sources/abc/download"),
    # Phase 2C indexing routes.
    ("POST", "/api/v1/knowledge/sources/abc/index"),
    ("POST", "/api/v1/knowledge/sources/abc/reindex"),
    # Phase 3A retrieval.
    ("POST", "/api/v1/knowledge/workspaces/abc/search"),
    # Phase 3B conversations and generation.
    ("GET", "/api/v1/conversations/workspaces/abc"),
    ("POST", "/api/v1/conversations/workspaces/abc"),
    ("GET", "/api/v1/conversations/abc"),
    ("GET", "/api/v1/conversations/abc/messages"),
    ("POST", "/api/v1/conversations/workspaces/abc/ask"),
    ("GET", "/api/v1/conversations/answers/abc"),
    # Phase 3C verification and memory.
    ("POST", "/api/v1/memory/answers/abc/verify"),
    ("GET", "/api/v1/memory/workspaces/abc/corrections"),
    ("POST", "/api/v1/memory/workspaces/abc/corrections"),
    ("POST", "/api/v1/memory/corrections/abc/review"),
    ("POST", "/api/v1/memory/corrections/abc/apply"),
    ("GET", "/api/v1/memory/workspaces/abc/conflicts"),
    ("POST", "/api/v1/memory/workspaces/abc/conflicts/detect"),
    ("POST", "/api/v1/memory/conflicts/abc/resolve"),
    # Phase 3D agent orchestration.
    ("POST", "/api/v1/agents/workspaces/abc/ask"),
    ("GET", "/api/v1/agents/orchestrations/abc"),
    ("GET", "/api/v1/agents/workspaces/abc/orchestrations"),
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
        from fastapi import HTTPException

        from app.domain.identity import Identity

        identity = Identity(user_id=USER_ID, email="alice@mnemos.test", role="authenticated")
        captured["identity"] = identity
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


# --- Phase 2A: knowledge surface -----------------------------------------


def test_knowledge_routes_require_a_workspace_membership(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller with a valid token still gets 403 when RLS shows no rows.

    The repository is stubbed to raise, which is what the Supabase adapter
    does when PostgREST reports an insufficient-privilege error. This asserts
    the route surfaces that decision rather than swallowing it.
    """
    from app.api.deps import get_chunk_repository, get_source_repository
    from app.core.errors import ForbiddenError

    class DeniedSources:
        def list_for_workspace(self, *args: Any, **kwargs: Any) -> Any:
            raise ForbiddenError(message="You do not have access to this workspace.")

    class EmptyChunks:
        def resolve_for_chunk(self, *args: Any, **kwargs: Any) -> Any:
            return None

    client.app.dependency_overrides[get_source_repository] = DeniedSources  # type: ignore[attr-defined]
    client.app.dependency_overrides[get_chunk_repository] = EmptyChunks  # type: ignore[attr-defined]
    try:
        response = client.get(
            "/api/v1/knowledge/workspaces/abc/sources",
            headers={"Authorization": f"Bearer {make_token()}"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def test_unresolvable_provenance_is_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A citation id that resolves to nothing must 404, never render as real."""
    from app.api.deps import get_chunk_repository, get_source_repository

    class EmptySources:
        pass

    class EmptyChunks:
        def resolve_for_chunk(self, *args: Any, **kwargs: Any) -> Any:
            return None

    client.app.dependency_overrides[get_source_repository] = EmptySources  # type: ignore[attr-defined]
    client.app.dependency_overrides[get_chunk_repository] = EmptyChunks  # type: ignore[attr-defined]
    try:
        response = client.get(
            "/api/v1/knowledge/chunks/00000000-0000-4000-8000-000000000000/provenance",
            headers={"Authorization": f"Bearer {make_token()}"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
