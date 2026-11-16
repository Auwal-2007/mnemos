"""Retrieval service (Phase 3A).

Turns a user's question into ranked, citable passages. This is the only place
that decides *which* evidence exists for a question; Phase 3B may only write
answers from what this returns, and Phase 3C may only verify claims against it.

Design rules encoded here
-------------------------
* **Membership is checked before retrieval.** RLS already prevents a
  non-member from seeing rows, but an explicit role check gives a truthful 403
  instead of an empty list, so the UI can distinguish "you cannot ask here"
  from "nothing matched".
* **No embedding provider is not a failure.** A deployment without embeddings
  still retrieves lexically. The result says so via `degraded_reason` rather
  than pretending hybrid search ran (UI honesty rule).
* **An empty result is a valid result.** The service never raises for "nothing
  found"; deciding whether to answer is the generation stage's job, and FR-010
  requires that decision to be explicit rather than an error.
* **The query is never rewritten into SQL.** It travels as a bound parameter
  to one function with three scalar arguments.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors import ForbiddenError, NotFoundError
from app.domain.knowledge import InformationStatus, SourceKind
from app.domain.models import WorkspaceRole
from app.domain.retrieval import RetrievalResult, RetrievalSource, RetrievedPassage
from app.infrastructure.embeddings import EmbeddingNotConfiguredError, EmbeddingProvider
from app.repositories.base import WorkspaceRepository

logger = logging.getLogger("mnemos.retrieval")


class PassageSearch(Protocol):
    """The single database operation retrieval needs.

    Implemented by `SupabaseRetrievalRepository`, which calls the
    `hybrid_search_chunks` SQL function. A caller cannot supply SQL.
    """

    def search(
        self,
        *,
        workspace_id: str,
        query: str,
        query_embedding: Sequence[float] | None,
        candidate_count: int,
        limit: int,
        include_superseded: bool,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class RetrievalOptions:
    """Validated retrieval parameters."""

    limit: int = 10
    candidate_count: int = 30
    include_superseded: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not 1 <= self.candidate_count <= 200:
            raise ValueError("candidate_count must be between 1 and 200")


class RetrievalService:
    """Hybrid retrieval over one workspace."""

    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        search: PassageSearch,
        provider: EmbeddingProvider | None,
    ) -> None:
        self._workspaces = workspaces
        self._search = search
        self._provider = provider

    async def search(
        self,
        *,
        workspace_id: str,
        user_id: str,
        query: str,
        options: RetrievalOptions | None = None,
    ) -> RetrievalResult:
        """Retrieve passages relevant to ``query``.

        Raises Forbidden when the caller is not a member, and NotFound when the
        workspace does not exist for them. An unauthorized caller sees the same
        answer a missing workspace would give.
        """
        options = options or RetrievalOptions()
        cleaned = query.strip()
        if not cleaned:
            raise NotFoundError(message="Enter a question to search for.")

        self._require_member(workspace_id, user_id)

        embedding, degraded = await self._embed(cleaned)
        rows = self._search.search(
            workspace_id=workspace_id,
            query=cleaned,
            query_embedding=embedding,
            candidate_count=options.candidate_count,
            limit=options.limit,
            include_superseded=options.include_superseded,
        )

        passages = [self._passage(row, workspace_id) for row in rows]
        if degraded:
            logger.info("Retrieval ran without embeddings (workspace member request)")
        logger.info(
            "Retrieval complete (passages=%s hybrid=%s superseded=%s)",
            len(passages),
            embedding is not None,
            options.include_superseded,
        )
        return RetrievalResult(
            passages=passages,
            query=cleaned,
            candidate_count=options.candidate_count,
            limit=options.limit,
            include_superseded=options.include_superseded,
            hybrid=embedding is not None,
            degraded_reason=degraded,
            metadata={
                "retrievers": sorted({passage.matched_by.value for passage in passages}),
                "with_location": sum(1 for passage in passages if passage.has_location()),
            },
        )

    # --- internals -------------------------------------------------------

    def _require_member(self, workspace_id: str, user_id: str) -> None:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError(message="Workspace not found.")
        roles = {
            member.role
            for member in self._workspaces.list_members(workspace_id)
            if member.user_id == user_id
        }
        if not roles & {WorkspaceRole.OWNER, WorkspaceRole.EDITOR, WorkspaceRole.VIEWER}:
            raise ForbiddenError(message="You do not have access to this workspace.")

    async def _embed(self, query: str) -> tuple[list[float] | None, str | None]:
        """Embed the query, or explain why semantic retrieval was skipped.

        Query embedding failure must not fail the request: lexical retrieval is
        still a truthful, useful result. The reason is surfaced so the UI can
        show the degradation instead of hiding it.
        """
        if self._provider is None:
            return None, "Semantic search is not configured; results are lexical only."
        try:
            batch = await self._provider.embed([query])
        except EmbeddingNotConfiguredError:
            return None, "Semantic search is not configured; results are lexical only."
        except Exception as exc:  # degradation, never a request failure
            logger.warning(
                "Query embedding failed (%s); falling back to lexical", type(exc).__name__
            )
            return None, "Semantic search is temporarily unavailable; results are lexical only."
        if not batch.vectors:
            return None, "The embedding provider returned no vector; results are lexical only."
        return list(batch.vectors[0].values), None

    def _passage(self, row: dict[str, Any], workspace_id: str) -> RetrievedPassage:
        return RetrievedPassage(
            chunk_id=str(row["chunk_id"]),
            provenance_id=str(row["provenance_id"]),
            source_id=str(row["source_id"]),
            document_version_id=str(row["document_version_id"]),
            workspace_id=workspace_id,
            source_title=str(row["source_title"]),
            source_kind=SourceKind(row["source_kind"]),
            version_number=int(row["version_number"]),
            version_is_current=bool(row["version_is_current"]),
            information_status=InformationStatus(row["information_status"]),
            chunk_index=int(row["chunk_index"]),
            content=str(row["content"]),
            char_count=int(row["char_count"]),
            source_location=dict(row["source_location"] or {}),
            lexical_rank=_optional_int(row.get("lexical_rank")),
            semantic_rank=_optional_int(row.get("semantic_rank")),
            lexical_score=_optional_float(row.get("lexical_score")),
            semantic_similarity=_optional_float(row.get("semantic_similarity")),
            fused_score=float(row["rrf_score"]),
            matched_by=RetrievalSource.from_raw(str(row["matched_by"])),
        )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None
