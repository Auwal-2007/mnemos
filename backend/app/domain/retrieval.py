"""Retrieval domain models (Phase 3A).

A `RetrievedPassage` is what the retrieval stage hands to every later stage.
It is deliberately *not* an answer: it carries no generated text, only the
passage that was found, where it came from, and how it was ranked.

The provenance fields are not optional by accident. FR-011 requires that
knowledge items carry their origin, and Phase 4A will fail any answer whose
claims cannot be resolved to one of these passages. Making the fields
non-optional here means a retrieval result that cannot be cited cannot even be
constructed.

Scores are reported individually as well as fused:

    lexical_score       ts_rank_cd from PostgreSQL (higher is better, unbounded)
    semantic_similarity 1 - cosine distance (roughly -1..1, typically 0..1)
    fused_score         reciprocal-rank sum (bounded, comparable across queries)

The individual scores are exposed for diagnosis and for the evaluation in
Phase 4A, where being able to say *which* retriever found a passage matters.
They are never averaged, and callers must not treat them as comparable: only
`fused_score` is used for ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.knowledge import InformationStatus, SourceKind


class RetrievalSource(StrEnum):
    """Which retriever produced a passage."""

    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    BOTH = "both"

    @classmethod
    def from_raw(cls, value: str) -> RetrievalSource:
        try:
            return cls(value)
        except ValueError:
            # An unknown value means the database and this enum disagree. That
            # is a bug, not user input, so surface it rather than guessing.
            raise ValueError(f"Unknown retrieval source: {value!r}") from None


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """One passage returned by retrieval, with the identity needed to cite it."""

    chunk_id: str
    provenance_id: str
    source_id: str
    document_version_id: str
    workspace_id: str
    source_title: str
    source_kind: SourceKind
    version_number: int
    version_is_current: bool
    information_status: InformationStatus
    chunk_index: int
    content: str
    char_count: int
    source_location: dict[str, Any]
    lexical_rank: int | None
    semantic_rank: int | None
    lexical_score: float | None
    semantic_similarity: float | None
    fused_score: float
    matched_by: RetrievalSource

    @property
    def start_offset(self) -> int | None:
        """Character offset of the passage's start, when known."""
        return _as_int(self.source_location.get("start_offset"))

    @property
    def end_offset(self) -> int | None:
        """Character offset of the passage's end, when known."""
        return _as_int(self.source_location.get("end_offset"))

    @property
    def page(self) -> int | None:
        """Page number, when the original document had pages."""
        return _as_int(self.source_location.get("page"))

    def has_location(self) -> bool:
        """True when the passage can be pointed at precisely."""
        page = self.page
        start, end = self.start_offset, self.end_offset
        return page is not None or (start is not None and end is not None)


def _as_int(value: object) -> int | None:
    """Coerce a JSON scalar to int, or None when it is not a number.

    `source_location` arrives from JSON, so a value may be a string, a float or
    absent. Anything unparseable becomes None rather than raising: a passage
    with an unusable location is still valid evidence, it simply cannot be
    pinpointed, and the UI must say so.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """The outcome of one retrieval, including how it was performed.

    `degraded_reason` is set when a retriever could not be used (for example no
    embedding provider is configured). It exists so the UI and the API can say
    "lexical only" instead of implying full hybrid search silently ran.
    """

    passages: list[RetrievedPassage]
    query: str
    candidate_count: int
    limit: int
    include_superseded: bool
    hybrid: bool
    degraded_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.passages)

    @property
    def has_evidence(self) -> bool:
        """Whether anything was found at all.

        Not the same as "the question can be answered": Phase 3B decides that
        against the model's own reading of these passages.
        """
        return bool(self.passages)
