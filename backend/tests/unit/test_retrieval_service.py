"""Retrieval service tests (Phase 3A).

What is under test is the service's contract, not PostgreSQL's ranking:

* membership is enforced before any retrieval happens;
* a missing embedding provider degrades to lexical search **and says so**;
* an embedding failure degrades rather than failing the request;
* an empty result is a successful result, not an error;
* the passage rows are converted without inventing fields.

The SQL itself is exercised against real PostgreSQL in
`tests/integration/test_retrieval_live.py` and `scripts/verify-migrations.py`.
"""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.domain.knowledge import InformationStatus, SourceKind
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.domain.retrieval import RetrievalSource
from app.infrastructure.embeddings import (
    EmbeddingBatch,
    EmbeddingError,
    EmbeddingNotConfiguredError,
    EmbeddingVector,
)
from app.services.retrieval import RetrievalOptions, RetrievalService

NOW = None  # datetimes are irrelevant to these tests; repositories supply them
WS = "33333333-3333-4333-8333-333333333333"
USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def workspace(workspace_id: str = WS) -> Workspace:
    import datetime as dt

    stamp = dt.datetime(2026, 11, 15, tzinfo=dt.UTC)
    return Workspace(
        id=workspace_id,
        name="Research",
        slug="research",
        description=None,
        owner_id=USER,
        created_at=stamp,
        updated_at=stamp,
    )


def member(user_id: str = USER, role: WorkspaceRole = WorkspaceRole.OWNER) -> WorkspaceMember:
    import datetime as dt

    stamp = dt.datetime(2026, 11, 15, tzinfo=dt.UTC)
    return WorkspaceMember(
        workspace_id=WS,
        user_id=user_id,
        role=role,
        created_at=stamp,
    )


class FakeWorkspaces:
    def __init__(self, members: list[WorkspaceMember] | None = None, exists: bool = True) -> None:
        self._members = members if members is not None else [member()]
        self._exists = exists

    def get(self, workspace_id: str) -> Workspace | None:
        return workspace(workspace_id) if self._exists else None

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return self._members

    # Unused parts of the protocol are not needed by the service.
    def list_for_user(self, user_id: str) -> list[Workspace]:  # pragma: no cover
        return [workspace()]

    def create(self, *args: object, **kwargs: object) -> Workspace:  # pragma: no cover
        raise NotImplementedError

    def update(self, *args: object, **kwargs: object) -> Workspace | None:  # pragma: no cover
        raise NotImplementedError

    def delete(self, workspace_id: str) -> bool:  # pragma: no cover
        raise NotImplementedError


class FakeSearch:
    """Records the arguments retrieval passed down."""

    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        return self.rows


class FakeProvider:
    def __init__(self, *, fail: Exception | None = None, vectors: int = 1) -> None:
        self._fail = fail
        self._vectors = vectors
        self.calls = 0

    @property
    def dimension(self) -> int:
        return 8

    @property
    def model_id(self) -> str:
        return "fake-embed"

    async def embed(self, texts: object) -> EmbeddingBatch:
        self.calls += 1
        if self._fail is not None:
            raise self._fail
        return EmbeddingBatch(
            vectors=[EmbeddingVector(index=i, values=[0.1] * 8) for i in range(self._vectors)],
            model=self.model_id,
        )


def row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "chunk_id": "c-1",
        "provenance_id": "p-1",
        "source_id": "src-1",
        "document_version_id": "v-1",
        "source_title": "Report",
        "source_kind": "document",
        "version_number": 1,
        "version_is_current": True,
        "information_status": "current",
        "chunk_index": 0,
        "content": "Passport renewal needs a birth certificate.",
        "char_count": 41,
        "source_location": {"start_offset": 0, "end_offset": 41, "page": 2},
        "lexical_rank": 1,
        "semantic_rank": None,
        "lexical_score": 0.6,
        "semantic_similarity": None,
        "rrf_score": 0.0164,
        "matched_by": "lexical",
    }
    base.update(overrides)
    return base


def service(
    *,
    members: list[WorkspaceMember] | None = None,
    rows: list[dict[str, object]] | None = None,
    provider: FakeProvider | None = None,
    exists: bool = True,
) -> tuple[RetrievalService, FakeSearch]:
    search = FakeSearch(rows)
    return (
        RetrievalService(
            workspaces=FakeWorkspaces(members, exists),  # type: ignore[arg-type]
            search=search,
            provider=provider,  # type: ignore[arg-type]
        ),
        search,
    )


async def test_returns_passages_with_full_provenance() -> None:
    svc, _ = service(rows=[row()])
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")

    assert result.total == 1
    passage = result.passages[0]
    assert passage.chunk_id == "c-1"
    assert passage.provenance_id == "p-1"
    assert passage.source_kind is SourceKind.DOCUMENT
    assert passage.information_status is InformationStatus.CURRENT
    assert passage.page == 2
    assert passage.start_offset == 0
    assert passage.end_offset == 41
    assert passage.has_location() is True
    assert result.has_evidence is True


async def test_matched_by_is_parsed_into_enum() -> None:
    svc, _ = service(rows=[row(matched_by="both")])
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")
    assert result.passages[0].matched_by is RetrievalSource.BOTH


async def test_unknown_matched_by_value_surfaces_rather_than_guesses() -> None:
    svc, _ = service(rows=[row(matched_by="telepathy")])
    with pytest.raises(ValueError):
        await svc.search(workspace_id=WS, user_id=USER, query="passport")


async def test_non_member_is_forbidden_before_retrieval() -> None:
    svc, search = service(members=[member(OTHER)])
    with pytest.raises(ForbiddenError):
        await svc.search(workspace_id=WS, user_id=USER, query="passport")
    assert search.calls == [], "retrieval must not run for an unauthorized caller"


async def test_missing_workspace_is_not_found() -> None:
    svc, search = service(exists=False)
    with pytest.raises(NotFoundError):
        await svc.search(workspace_id=WS, user_id=USER, query="passport")
    assert search.calls == []


async def test_viewer_may_search() -> None:
    svc, _ = service(members=[member(USER, WorkspaceRole.VIEWER)], rows=[row()])
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")
    assert result.total == 1


async def test_blank_query_is_rejected() -> None:
    svc, search = service(rows=[row()])
    with pytest.raises(NotFoundError):
        await svc.search(workspace_id=WS, user_id=USER, query="   ")
    assert search.calls == []


async def test_without_provider_retrieval_is_lexical_and_says_so() -> None:
    svc, search = service(rows=[row()], provider=None)
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")

    assert result.hybrid is False
    assert result.degraded_reason is not None
    assert "lexical" in result.degraded_reason
    assert search.calls[0]["query_embedding"] is None


async def test_with_provider_the_query_is_embedded() -> None:
    provider = FakeProvider()
    svc, search = service(rows=[row()], provider=provider)
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")

    assert result.hybrid is True
    assert result.degraded_reason is None
    assert provider.calls == 1
    assert search.calls[0]["query_embedding"] == [0.1] * 8


async def test_embedding_failure_degrades_to_lexical_without_failing() -> None:
    svc, search = service(rows=[row()], provider=FakeProvider(fail=EmbeddingError()))
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")

    assert result.hybrid is False
    assert result.degraded_reason is not None
    assert result.total == 1
    assert search.calls[0]["query_embedding"] is None


async def test_unconfigured_provider_degrades_with_a_specific_reason() -> None:
    svc, _ = service(rows=[row()], provider=FakeProvider(fail=EmbeddingNotConfiguredError()))
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")
    assert result.hybrid is False
    assert result.degraded_reason is not None


async def test_empty_vector_list_degrades() -> None:
    svc, search = service(rows=[], provider=FakeProvider(vectors=0))
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")
    assert result.hybrid is False
    assert search.calls[0]["query_embedding"] is None


async def test_no_matches_is_a_successful_empty_result() -> None:
    """An empty result is a successful search in a fully healthy configuration.

    It is not an error and not a degradation: the deployment had embeddings,
    both retrievers ran, and nothing matched. Only Phase 3B may turn this into
    an abstention.
    """
    svc, _ = service(rows=[], provider=FakeProvider())
    result = await svc.search(workspace_id=WS, user_id=USER, query="unfindable")

    assert result.total == 0
    assert result.passages == []
    assert result.has_evidence is False
    assert result.hybrid is True
    assert result.degraded_reason is None


async def test_options_are_passed_through() -> None:
    svc, search = service(rows=[row()])
    await svc.search(
        workspace_id=WS,
        user_id=USER,
        query="passport",
        options=RetrievalOptions(limit=3, candidate_count=7, include_superseded=True),
    )
    assert search.calls[0]["limit"] == 3
    assert search.calls[0]["candidate_count"] == 7
    assert search.calls[0]["include_superseded"] is True


async def test_query_is_trimmed_before_search() -> None:
    svc, search = service(rows=[row()])
    result = await svc.search(workspace_id=WS, user_id=USER, query="  passport  ")
    assert result.query == "passport"
    assert search.calls[0]["query"] == "passport"


@pytest.mark.parametrize(
    ("limit", "candidate_count"),
    [(0, 30), (101, 30), (10, 0), (10, 201)],
)
def test_options_reject_out_of_range_values(limit: int, candidate_count: int) -> None:
    with pytest.raises(ValueError):
        RetrievalOptions(limit=limit, candidate_count=candidate_count)


async def test_metadata_counts_how_many_passages_have_locations() -> None:
    rows = [row(), row(chunk_id="c-2", provenance_id="p-2", source_location={})]
    svc, _ = service(rows=rows, provider=FakeProvider())
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")

    # The second row carries an empty location, so exactly one passage is
    # pinpointable. Reporting 2 would make the UI claim a page it cannot show.
    assert result.metadata["with_location"] == 1
    assert result.metadata["retrievers"] == ["lexical"]


async def test_passage_without_location_is_still_valid_evidence() -> None:
    svc, _ = service(rows=[row(source_location={})])
    result = await svc.search(workspace_id=WS, user_id=USER, query="passport")
    passage = result.passages[0]

    assert passage.has_location() is False
    assert passage.page is None
    assert passage.start_offset is None
