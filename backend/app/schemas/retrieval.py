"""Retrieval API schemas (Phase 3A)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """A retrieval request.

    The query is plain text. It is never interpreted as SQL, a filter
    expression or a template — it reaches the database as a bound parameter.
    """

    query: str = Field(min_length=1, max_length=2000, description="Question or search text")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum passages to return")
    candidate_count: int = Field(
        default=30,
        ge=1,
        le=200,
        description="Passages each retriever contributes before fusion",
    )
    include_superseded: bool = Field(
        default=False,
        description=(
            "Include passages whose information status is superseded or archived. "
            "Off by default so stale material is not presented as current."
        ),
    )


class RetrievalScoreResponse(BaseModel):
    """Per-retriever scores. Reported, never averaged."""

    lexical_rank: int | None = None
    semantic_rank: int | None = None
    lexical_score: float | None = None
    semantic_similarity: float | None = None
    fused_score: float


class RetrievedPassageResponse(BaseModel):
    """One passage of evidence.

    `content` is the exact chunk text. The location fields identify where it
    sits in the original version so the UI can show page and offsets, and so a
    later answer can cite it without guessing.
    """

    chunk_id: str
    provenance_id: str
    source_id: str
    document_version_id: str
    source_title: str
    source_kind: Literal["document", "note"]
    version_number: int
    version_is_current: bool
    information_status: str
    chunk_index: int
    content: str
    char_count: int
    source_location: dict[str, Any] = Field(default_factory=dict)
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    matched_by: Literal["lexical", "semantic", "both"]
    scores: RetrievalScoreResponse


class SearchResponse(BaseModel):
    """Retrieval result plus the facts needed to describe it honestly.

    `hybrid` is false when semantic retrieval could not run, and
    `degraded_reason` then explains why. The UI must present that rather than
    claiming a full hybrid search took place.
    """

    query: str
    passages: list[RetrievedPassageResponse]
    total: int
    limit: int
    candidate_count: int
    include_superseded: bool
    hybrid: bool
    degraded_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
