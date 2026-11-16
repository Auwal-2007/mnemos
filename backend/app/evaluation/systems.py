"""The two retrieval systems under comparison (Phase 4A).

Fairness is the whole design constraint here, so it is worth stating exactly
what each system is given and what it is not.

What both systems share
-----------------------
* the same corpus, chunked by the same algorithm into the same passages
* the same question set
* the same ``k`` (top-k passages reported)
* the same retriever family in any given run — when no embedding provider is
  configured, *both* run lexically, so the comparison never silently handicaps
  one side by denying it a retriever the other has
* the same PostgreSQL instance and the same full-text index

Where they differ
-----------------
MNEMOS
    Hybrid reciprocal-rank fusion (``hybrid_search_chunks``), candidates from a
    wider pool fused by rank, superseded passes excluded by default, every
    passage carrying provenance identity.

Baseline
    "Conventional RAG": one retriever, plain top-k by raw relevance score, no
    fusion, no supersession filtering, no relevance floor.

The baseline is deliberately *not* strawmanned. It uses the identical
PostgreSQL full-text ranking function at the identical ``k``; on a purely
lexical corpus it can and does win on some metrics. That is reported rather
than tuned away. The differences that are architecturally real are the ones
listed above, and the report states which measured differences follow from
them.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Hit:
    """One retrieved passage, reduced to what scoring needs."""

    chunk_id: str
    document_title: str
    content: str
    score: float
    rank: int
    #: The retriever's own relevance strength before fusion. RRF deliberately
    #: discards magnitude, so a fused score cannot answer "was this a strong
    #: match or a stray common word?" — which is exactly the question an
    #: evidence gate has to answer.
    strength: float = 0.0


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """What a system returned for one question, plus its cost."""

    question: str
    hits: tuple[Hit, ...]
    latency_ms: float
    mode: str
    #: Names of the retrievers that actually ran. Recorded so a reader can tell
    #: a lexical-only run from a hybrid one without reading the code.
    retrievers: tuple[str, ...] = ()
    notes: str = ""

    @property
    def titles(self) -> list[str]:
        """Document titles in rank order, first occurrence only.

        A document may contribute several passages; for document-level metrics
        counting it repeatedly would double-count one source as several.
        """
        seen: list[str] = []
        for hit in self.hits:
            if hit.document_title not in seen:
                seen.append(hit.document_title)
        return seen

    @property
    def strongest(self) -> float:
        """The highest retriever strength among returned passages."""
        return max((hit.strength for hit in self.hits), default=0.0)

    def sufficient(self, floor: float) -> bool:
        """Whether the evidence clears a relevance floor."""
        return bool(self.hits) and self.strongest >= floor

    @property
    def answered(self) -> bool:
        """Whether retrieval produced anything the system could answer from.

        This is *retrieval-level* abstention. It is not the same as the
        generation stage declining to answer, and the report keeps the two
        apart: only the former can be measured without a model.
        """
        return bool(self.hits)


class RetrievalSystem(Protocol):
    """Anything that turns a question into ranked passages."""

    name: str

    def retrieve(self, question: str, *, k: int) -> RetrievalOutcome: ...


class SqlExecutor(Protocol):
    """Minimal database access, so systems are testable without a live server."""

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]: ...


class MnemosSystem:
    """The shipped retrieval path: hybrid RRF through the real SQL function.

    Parameters mirror ``RetrievalOptions`` so a run cannot silently use settings
    the product would not use.
    """

    name = "mnemos"

    def __init__(
        self,
        db: SqlExecutor,
        *,
        workspace_id: str,
        candidate_count: int = 30,
        include_superseded: bool = False,
    ) -> None:
        self._db = db
        self._workspace = workspace_id
        self._candidates = candidate_count
        self._include_superseded = include_superseded

    def retrieve(self, question: str, *, k: int) -> RetrievalOutcome:
        started = time.perf_counter()
        rows = self._db.rows(
            "select chunk_id, source_title, content, rrf_score, matched_by,"
            " lexical_score"
            " from public.hybrid_search_chunks("
            " p_workspace_id => %s::uuid, p_query => %s, p_query_embedding => null,"
            " p_candidate_count => %s, p_limit => %s, p_include_superseded => %s)",
            (self._workspace, question, self._candidates, k, self._include_superseded),
        )
        elapsed = (time.perf_counter() - started) * 1000.0
        hits: list[Hit] = []
        for index, row in enumerate(rows, start=1):
            score = float(row["rrf_score"])
            hits.append(
                Hit(
                    chunk_id=str(row["chunk_id"]),
                    document_title=str(row["source_title"]),
                    content=str(row["content"]),
                    score=score,
                    rank=index,
                    strength=float(row.get("lexical_score") or 0.0),
                )
            )
        matched = sorted({str(row.get("matched_by", "")) for row in rows} - {""})
        return RetrievalOutcome(
            question=question,
            hits=tuple(hits),
            latency_ms=elapsed,
            mode="hybrid" if "semantic" in matched or "both" in matched else "lexical",
            retrievers=tuple(matched) or ("lexical",),
        )


class BaselineSystem:
    """Conventional RAG retrieval: single retriever, plain top-k, no fusion.

    Calls the same PostgreSQL ranking primitive directly. Choosing the same
    primitive is what makes the comparison about *architecture* rather than
    about which index happened to be better tuned.
    """

    name = "baseline"

    def __init__(
        self,
        db: SqlExecutor,
        *,
        workspace_id: str,
        include_superseded: bool = True,
    ) -> None:
        self._db = db
        self._workspace = workspace_id
        # A conventional pipeline does not model supersession, so by default it
        # sees every version — which is precisely how it can surface stale text.
        self._include_superseded = include_superseded

    def retrieve(self, question: str, *, k: int) -> RetrievalOutcome:
        started = time.perf_counter()
        status_clause = (
            "" if self._include_superseded else (" and p.information_status = 'current'")
        )
        # Query parsing is shared with MNEMOS on purpose. If the baseline parsed
        # questions differently it would lose for a reason that has nothing to
        # do with pipeline architecture, and the comparison would be worthless.
        # The baseline uses the relaxed parse, which is marginally *more*
        # permissive than MNEMOS's strict-first parse; if that helps anyone it
        # helps the baseline.
        rows = self._db.rows(
            "select c.id as chunk_id, s.title as source_title, c.content as content,"
            " ts_rank_cd(c.content_tsv,"
            " public.mnemos_lexical_query_relaxed(%s)) as score"
            " from public.chunks c"
            " join public.sources s on s.id = c.source_id"
            " join public.provenance_records p on p.chunk_id = c.id"
            " where c.workspace_id = %s::uuid"
            " and c.content_tsv @@ public.mnemos_lexical_query_relaxed(%s)"
            f"{status_clause}"
            " order by score desc, c.chunk_index asc"
            " limit %s",
            (question, self._workspace, question, k),
        )
        elapsed = (time.perf_counter() - started) * 1000.0
        hits = tuple(
            Hit(
                chunk_id=str(row["chunk_id"]),
                document_title=str(row["source_title"]),
                content=str(row["content"]),
                score=float(row["score"]),
                rank=index,
                strength=float(row["score"]),
            )
            for index, row in enumerate(rows, start=1)
        )
        return RetrievalOutcome(
            question=question,
            hits=hits,
            latency_ms=elapsed,
            mode="lexical",
            retrievers=("lexical",),
        )


@dataclass(slots=True)
class Comparison:
    """Both systems' outcomes for one question."""

    case_id: str
    category: str
    question: str
    expected_titles: tuple[str, ...]
    expect_abstention: bool
    mnemos: RetrievalOutcome
    baseline: RetrievalOutcome
    extra: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "BaselineSystem",
    "Comparison",
    "Hit",
    "MnemosSystem",
    "RetrievalOutcome",
    "RetrievalSystem",
    "SqlExecutor",
]
