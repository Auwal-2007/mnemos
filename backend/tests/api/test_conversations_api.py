"""Conversation and grounded-answer API tests (Phase 3B).

The provider is faked so these exercise the HTTP contract, not a model. The
generation *logic* is covered exhaustively in tests/unit/test_generation.py;
what is asserted here is what a client actually receives:

* an abstention is HTTP 200 with ``status="insufficient_evidence"``, because it
  is a correct outcome rather than an error;
* a claim and its evidence arrive in one response, so the UI can render a
  citation without a second request;
* a provider failure is a 502 with the canonical envelope and no fake answer;
* authentication and membership are enforced before any model call.

The repositories are replaced at the module boundary rather than at
`get_auth_context`, because the point is to test the routes' own behaviour.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_workspace_repository
from app.core.config import get_settings
from app.domain.conversation import (
    AgentRole,
    Conversation,
    ExecutionRecord,
    ExecutionStatus,
    Message,
    MessageRole,
)
from app.domain.knowledge import InformationStatus, SourceKind
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.domain.retrieval import RetrievalSource, RetrievedPassage
from app.main import create_app

SECRET = "test-jwt-secret-with-at-least-32-characters-long"
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
WS = "33333333-3333-4333-8333-333333333333"
CONV = "44444444-4444-4444-8444-444444444444"
PROV = "aaaaaaaa-0000-4000-8000-000000000001"
STAMP = dt.datetime(2026, 11, 15, tzinfo=dt.UTC)


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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijklm.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    # A model must be configured, otherwise the route correctly refuses with 503.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/model")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    get_settings.cache_clear()
    application = create_app()
    yield TestClient(application)
    get_settings.cache_clear()


OWNER = WorkspaceMember(
    workspace_id=WS, user_id=USER_ID, role=WorkspaceRole.OWNER, created_at=STAMP
)


class FakeWorkspaces:
    def __init__(self, members: list[WorkspaceMember] | None = None, exists: bool = True) -> None:
        self.members = members if members is not None else [OWNER]
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


def passage() -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id="chunk-1",
        provenance_id=PROV,
        source_id="src-1",
        document_version_id="ver-1",
        workspace_id=WS,
        source_title="Passport rules",
        source_kind=SourceKind.DOCUMENT,
        version_number=1,
        version_is_current=True,
        information_status=InformationStatus.CURRENT,
        chunk_index=0,
        content="Bring a birth certificate.",
        char_count=24,
        source_location={"start_offset": 0, "end_offset": 24, "page": 3},
        lexical_rank=1,
        semantic_rank=None,
        lexical_score=0.4,
        semantic_similarity=None,
        fused_score=0.016,
        matched_by=RetrievalSource.LEXICAL,
    )


def conversation(**overrides: Any) -> Conversation:
    base: dict[str, Any] = {
        "id": CONV,
        "workspace_id": WS,
        "owner_id": USER_ID,
        "title": "Passport questions",
        "agent_role": None,
        "is_archived": False,
        "created_at": STAMP,
        "updated_at": STAMP,
    }
    base.update(overrides)
    return Conversation(**base)


def message(role: MessageRole = MessageRole.USER, seq: int = 0, content: str = "q") -> Message:
    return Message(
        id=f"msg-{seq}",
        conversation_id=CONV,
        workspace_id=WS,
        role=role,
        content=content,
        sequence_number=seq,
        execution_id=None,
        created_at=STAMP,
    )


def execution() -> ExecutionRecord:
    return ExecutionRecord(
        id="exec-1",
        workspace_id=WS,
        conversation_id=CONV,
        agent_role=AgentRole.ORCHESTRATOR,
        purpose="answer_generation",
        model_id="test/model",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=120,
        prompt_tokens=100,
        completion_tokens=40,
        total_tokens=140,
    )


def patch_services(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, *, behaviours: dict[str, Any]
) -> dict[str, Any]:
    """Replace the repository and generation classes with recording fakes.

    `behaviours` selects the generation outcome: "answered", "abstain", "fail".
    Returns a record of calls so tests can assert nothing was called.
    """
    from app.api.v1 import conversations as module

    record: dict[str, Any] = {"asked": [], "created": []}

    class FakeConversations:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def list_for_workspace(
            self, workspace_id: str, *, limit: int = 50, offset: int = 0
        ) -> list[Conversation]:
            return [conversation()]

        def get(self, conversation_id: str) -> Conversation | None:
            return conversation(id=conversation_id)

        def create(
            self, *, workspace_id: str, owner_id: str, title: str, agent_role: Any = None
        ) -> Conversation:
            record["created"].append(title)
            return conversation(title=title, agent_role=agent_role)

        def touch(self, conversation_id: str) -> None:
            return None

        def list_messages(self, conversation_id: str) -> list[Message]:
            return [message()]

        def next_sequence_number(self, conversation_id: str) -> int:
            return 0

        def append_message(self, **kwargs: Any) -> Message:
            return message(
                role=kwargs["role"], seq=kwargs["sequence_number"], content=kwargs["content"]
            )

    class FakeAnswers:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def record_execution(self, record_: Any) -> ExecutionRecord:
            return execution()

        def save_answer(self, **kwargs: Any) -> str:
            return "answer-1"

        def get_answer(self, answer_id: str) -> dict[str, Any] | None:
            return None

        def list_claims(self, answer_id: str) -> list[Any]:
            return []

    class FakeRetrieval:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def search(self, **kwargs: Any) -> Any:
            from app.domain.retrieval import RetrievalResult

            rows = [] if behaviours.get("no_evidence") else [passage()]
            return RetrievalResult(
                passages=rows,
                query=str(kwargs["query"]),
                candidate_count=30,
                limit=10,
                include_superseded=False,
                hybrid=False,
            )

    class FakeGeneration:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def answer_question(self, **kwargs: Any) -> Any:
            from app.domain.conversation import (
                AnswerOutcome,
                AnswerStatus,
                CitationDraft,
                ClaimDraft,
            )
            from app.services.generation import GenerationOutcome

            record["asked"].append(kwargs["question"])
            if behaviours.get("fail"):
                from app.services.generation import GenerationFailedError

                raise GenerationFailedError(message="upstream unavailable")
            if behaviours.get("no_evidence") or behaviours.get("abstain"):
                return GenerationOutcome(
                    outcome=AnswerOutcome(
                        answer_id="answer-1",
                        status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                        content="I cannot answer that from the stored evidence.",
                        abstention_reason="No relevant passages.",
                        claims=[],
                        evidence_considered=0,
                        evidence_cited=0,
                        citations_by_claim={},
                        passages=[],
                    ),
                    execution=execution(),
                    model_reported="test/model",
                )
            claim = ClaimDraft(
                index=0,
                text="A birth certificate is required.",
                citations=[CitationDraft(provenance_id=PROV, quoted_text=None, relevance=None)],
            )
            return GenerationOutcome(
                outcome=AnswerOutcome(
                    answer_id="answer-1",
                    status=AnswerStatus.ANSWERED,
                    content="A birth certificate is required.",
                    abstention_reason=None,
                    claims=[claim],
                    evidence_considered=1,
                    evidence_cited=1,
                    citations_by_claim={claim.text: [PROV]},
                    passages=[passage()],
                ),
                execution=execution(),
                model_reported="test/model",
            )

    monkeypatch.setattr(module, "SupabaseConversationRepository", FakeConversations)
    monkeypatch.setattr(module, "SupabaseAnswerRepository", FakeAnswers)
    monkeypatch.setattr(module, "SupabaseRetrievalRepository", FakeRetrieval)
    monkeypatch.setattr(module, "RetrievalService", lambda **kwargs: FakeRetrieval())
    monkeypatch.setattr(module, "GenerationService", lambda **kwargs: FakeGeneration())
    return record


def override_workspaces(client: TestClient, repository: FakeWorkspaces) -> None:
    client.app.dependency_overrides[get_workspace_repository] = lambda: repository  # type: ignore[attr-defined]


# --- authentication ------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/api/v1/conversations/workspaces/{WS}"),
        ("POST", f"/api/v1/conversations/workspaces/{WS}"),
        ("GET", f"/api/v1/conversations/{CONV}"),
        ("GET", f"/api/v1/conversations/{CONV}/messages"),
        ("POST", f"/api/v1/conversations/workspaces/{WS}/ask"),
        ("GET", "/api/v1/conversations/answers/answer-1"),
    ],
)
def test_every_route_requires_authentication(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- grounded answer -----------------------------------------------------


def test_answered_response_carries_claims_with_evidence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    override_workspaces(client, FakeWorkspaces())
    patch_services(client, monkeypatch, behaviours={})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask",
            json={"question": "What do I need?"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["status"] == "answered"
    assert body["answer"]["claims"][0]["text"]
    citation = body["answer"]["claims"][0]["citations"][0]
    assert citation["provenance_id"] == PROV
    assert citation["source_title"] == "Passport rules"
    assert citation["page"] == 3
    assert citation["excerpt"] == "Bring a birth certificate."
    assert body["answer"]["execution"]["model_id"] == "test/model"


def test_abstention_is_200_not_an_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal to answer is a correct result and must not look like a fault."""
    override_workspaces(client, FakeWorkspaces())
    patch_services(client, monkeypatch, behaviours={"no_evidence": True})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask",
            json={"question": "unfindable"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["status"] == "insufficient_evidence"
    assert body["answer"]["abstention_reason"]
    assert body["answer"]["claims"] == []
    assert body["answer"]["evidence"] == []


def test_model_abstention_is_also_200(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    override_workspaces(client, FakeWorkspaces())
    patch_services(client, monkeypatch, behaviours={"abstain": True})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask",
            json={"question": "q"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
    assert response.status_code == 200
    assert response.json()["answer"]["status"] == "insufficient_evidence"


def test_provider_failure_is_502_with_no_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    override_workspaces(client, FakeWorkspaces())
    patch_services(client, monkeypatch, behaviours={"fail": True})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask",
            json={"question": "q"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "generation_failed"
    assert "answer" not in response.json()


# --- authorization -------------------------------------------------------


def test_non_member_cannot_ask(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    outsider = WorkspaceMember(
        workspace_id=WS, user_id=OTHER_ID, role=WorkspaceRole.OWNER, created_at=STAMP
    )
    override_workspaces(client, FakeWorkspaces([outsider]))
    record = patch_services(client, monkeypatch, behaviours={})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask",
            json={"question": "q"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 403
    assert record["asked"] == [], "generation ran for a non-member"


def test_missing_workspace_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    override_workspaces(client, FakeWorkspaces(exists=False))
    patch_services(client, monkeypatch, behaviours={})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask",
            json={"question": "q"},
            headers=headers(),
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
    assert response.status_code == 404


# --- validation ----------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "x" * 4001},
        {"question": "ok", "limit": 0},
        {"question": "ok", "limit": 51},
        {"question": "ok", "agent_role": "wizard"},
    ],
)
def test_invalid_ask_payloads_are_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    override_workspaces(client, FakeWorkspaces())
    record = patch_services(client, monkeypatch, behaviours={})
    try:
        response = client.post(
            f"/api/v1/conversations/workspaces/{WS}/ask", json=payload, headers=headers()
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert record["asked"] == []


# --- listing -------------------------------------------------------------


def test_list_conversations_returns_items(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    override_workspaces(client, FakeWorkspaces())
    patch_services(client, monkeypatch, behaviours={})
    try:
        response = client.get(f"/api/v1/conversations/workspaces/{WS}", headers=headers())
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Passport questions"


def test_conversation_routes_are_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/conversations/workspaces/{workspace_id}/ask" in paths
    assert "/api/v1/conversations/{conversation_id}/messages" in paths
