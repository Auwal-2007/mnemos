"""Retrieval endpoint tests (Phase 3A).

These exercise the HTTP surface: authentication, request validation, response
shape and the honest reporting of a degraded (lexical-only) run. The database
behaviour underneath is covered by the integration test and the migration
verifier.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_workspace_repository
from app.core.config import get_settings
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.main import create_app

SECRET = "test-jwt-secret-with-at-least-32-characters-long"
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
WS = "33333333-3333-4333-8333-333333333333"

STAMP = dt.datetime(2026, 11, 15, tzinfo=dt.UTC)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijklm.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-anon")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    # No embedding credentials: retrieval must run lexically and say so.
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    get_settings.cache_clear()

    application = create_app()
    yield TestClient(application)
    get_settings.cache_clear()


def token(sub: str = USER_ID) -> str:
    return jwt.encode(
        {
            "sub": sub,
            "email": "alice@mnemos.test",
            "role": "authenticated",
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )


def headers(sub: str = USER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(sub)}"}


class FakeWorkspaceRepository:
    """Membership fixture. RLS is stubbed; the real policy is verified live."""

    def __init__(self, members: list[WorkspaceMember], exists: bool = True) -> None:
        self.members = members
        self.exists = exists

    def get(self, workspace_id: str) -> Workspace | None:
        if not self.exists:
            return None
        return Workspace(
            id=workspace_id,
            owner_id=USER_ID,
            name="Research",
            slug="research",
            description=None,
            created_at=STAMP,
            updated_at=STAMP,
        )

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return self.members


OWNER = WorkspaceMember(
    workspace_id=WS, user_id=USER_ID, role=WorkspaceRole.OWNER, created_at=STAMP
)


class _FakeSearchExpectation:
    """Patch the retrieval repository with a recorded stub."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []


def _patch_search(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> _FakeSearchExpectation:
    from app.api.v1 import retrieval as retrieval_module

    recorder = _FakeSearchExpectation(rows)

    class Stub:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def search(self, **kwargs: Any) -> list[dict[str, Any]]:
            recorder.calls.append(kwargs)
            return recorder.rows

    monkeypatch.setattr(retrieval_module, "SupabaseRetrievalRepository", Stub)
    return recorder


ROW: dict[str, Any] = {
    "chunk_id": "c-1",
    "provenance_id": "p-1",
    "source_id": "src-1",
    "document_version_id": "v-1",
    "source_title": "Passport rules",
    "source_kind": "note",
    "version_number": 2,
    "version_is_current": True,
    "information_status": "current",
    "chunk_index": 3,
    "content": "A passport renewal requires a birth certificate.",
    "char_count": 48,
    "source_location": {"start_offset": 10, "end_offset": 58, "page": 4},
    "lexical_rank": 1,
    "semantic_rank": None,
    "lexical_score": 0.75,
    "semantic_similarity": None,
    "rrf_score": 0.016393,
    "matched_by": "lexical",
}


def test_search_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/api/v1/knowledge/workspaces/{WS}/search", json={"query": "passport"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_search_returns_evidence_with_provenance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.app.dependency_overrides[get_workspace_repository] = (  # type: ignore[attr-defined]
        lambda: FakeWorkspaceRepository([OWNER])
    )
    _patch_search(client, monkeypatch, [ROW])
    try:
        response = client.post(
            f"/api/v1/knowledge/workspaces/{WS}/search",
            json={"query": "passport renewal"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    passage = body["passages"][0]
    assert passage["provenance_id"] == "p-1"
    assert passage["source_title"] == "Passport rules"
    assert passage["page"] == 4
    assert passage["start_offset"] == 10
    assert passage["end_offset"] == 58
    assert passage["version_number"] == 2
    assert passage["version_is_current"] is True
    assert passage["scores"]["fused_score"] == pytest.approx(0.016393)
    assert passage["scores"]["semantic_similarity"] is None


def test_lexical_only_run_is_reported_honestly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no embedding provider the response must not claim hybrid search."""
    client.app.dependency_overrides[get_workspace_repository] = (  # type: ignore[attr-defined]
        lambda: FakeWorkspaceRepository([OWNER])
    )
    recorder = _patch_search(client, monkeypatch, [ROW])
    try:
        response = client.post(
            f"/api/v1/knowledge/workspaces/{WS}/search",
            json={"query": "passport"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    body = response.json()
    assert body["hybrid"] is False
    assert "lexical only" in body["degraded_reason"]
    assert recorder.calls[0]["query_embedding"] is None


def test_non_member_gets_forbidden(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.app.dependency_overrides[get_workspace_repository] = (  # type: ignore[attr-defined]
        lambda: FakeWorkspaceRepository(
            [
                WorkspaceMember(
                    workspace_id=WS,
                    user_id=OTHER_ID,
                    role=WorkspaceRole.OWNER,
                    created_at=STAMP,
                )
            ]
        )
    )
    recorder = _patch_search(client, monkeypatch, [ROW])
    try:
        response = client.post(
            f"/api/v1/knowledge/workspaces/{WS}/search",
            json={"query": "passport"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert recorder.calls == [], "no retrieval may occur for a non-member"


def test_missing_workspace_is_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.app.dependency_overrides[get_workspace_repository] = (  # type: ignore[attr-defined]
        lambda: FakeWorkspaceRepository([], exists=False)
    )
    _patch_search(client, monkeypatch, [ROW])
    try:
        response = client.post(
            f"/api/v1/knowledge/workspaces/{WS}/search",
            json={"query": "passport"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": ""},
        {"query": "x" * 2001},
        {"query": "ok", "limit": 0},
        {"query": "ok", "limit": 101},
        {"query": "ok", "candidate_count": 0},
        {"query": "ok", "candidate_count": 500},
    ],
)
def test_invalid_requests_are_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    client.app.dependency_overrides[get_workspace_repository] = (  # type: ignore[attr-defined]
        lambda: FakeWorkspaceRepository([OWNER])
    )
    recorder = _patch_search(client, monkeypatch, [])
    try:
        response = client.post(
            f"/api/v1/knowledge/workspaces/{WS}/search", json=payload, headers=headers()
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert recorder.calls == []


def test_empty_result_is_200_with_no_passages(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.app.dependency_overrides[get_workspace_repository] = (  # type: ignore[attr-defined]
        lambda: FakeWorkspaceRepository([OWNER])
    )
    _patch_search(client, monkeypatch, [])
    try:
        response = client.post(
            f"/api/v1/knowledge/workspaces/{WS}/search",
            json={"query": "nothing matches this"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 200
    assert response.json()["passages"] == []
    assert response.json()["total"] == 0


def test_search_route_is_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/knowledge/workspaces/{workspace_id}/search" in schema["paths"]
