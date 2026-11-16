"""Conversation and answer domain models (Phase 3B).

These mirror the Phase 3B tables but stay independent of Pydantic and of the
database driver.

The central idea is that an answer is not a string. It is a set of claims, each
of which either cites specific evidence or is visibly unsupported. That is what
makes FR-006 inspectable and what Phase 3C verifies claim by claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.knowledge import SourceKind
from app.domain.retrieval import RetrievedPassage


class AgentRole(StrEnum):
    """The named roles in the system.

    A role is a configured capability with its own model and prompt, not a
    separate process. Direct specialist chat and orchestration both use these.
    """

    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    CRITIC = "critic"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AnswerStatus(StrEnum):
    """How an answer came to exist. `insufficient_evidence` is a success path."""

    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REFUSED = "refused"
    FAILED = "failed"


class ClaimSupport(StrEnum):
    """Verification verdict for one claim (Phase 3C writes these)."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class CitationDraft:
    """A citation the model produced: a provenance id and optional quote."""

    provenance_id: str
    quoted_text: str | None
    relevance: float | None


@dataclass(frozen=True, slots=True)
class ClaimDraft:
    """One claim before persistence."""

    index: int
    text: str
    citations: list[CitationDraft]

    @property
    def citation_ids(self) -> list[str]:
        return [citation.provenance_id for citation in self.citations]


@dataclass(frozen=True, slots=True)
class Claim:
    """A persisted claim, with its verification state."""

    id: str
    answer_id: str
    claim_index: int
    text: str
    support: ClaimSupport
    verification_note: str | None
    citations: list[CitationDraft] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """An answer as produced by the generation service, before persistence."""

    status: AnswerStatus
    content: str
    abstention_reason: str | None
    claims: list[ClaimDraft]
    evidence_considered: int
    evidence_cited: int

    @property
    def is_abstention(self) -> bool:
        return self.status is AnswerStatus.INSUFFICIENT_EVIDENCE


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    """The answer as returned to the API, with its evidence attached.

    `passages` is the evidence the answer was generated from, so the UI can show
    the exact passages a claim cites without a second request. It is empty for
    an abstention that occurred before any model call.
    """

    answer_id: str
    status: AnswerStatus
    content: str
    abstention_reason: str | None
    claims: list[ClaimDraft]
    evidence_considered: int
    evidence_cited: int
    citations_by_claim: dict[str, list[str]]
    passages: list[RetrievedPassage]
    execution: ExecutionRecord | None = None

    @property
    def is_abstention(self) -> bool:
        return self.status is AnswerStatus.INSUFFICIENT_EVIDENCE


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """One model invocation (FR-014). `id` is empty until persisted."""

    id: str
    workspace_id: str
    conversation_id: str | None
    agent_role: AgentRole
    purpose: str
    model_id: str
    status: ExecutionStatus
    provider: str = "openrouter"
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    attempt_count: int = 1
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Conversation:
    """A conversation thread."""

    id: str
    workspace_id: str
    owner_id: str
    title: str
    agent_role: AgentRole | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Message:
    """One conversation turn."""

    id: str
    conversation_id: str
    workspace_id: str
    role: MessageRole
    content: str
    sequence_number: int
    execution_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceView:
    """A passage as presented alongside an answer.

    Carries enough to render a citation that a reader can check: title, page,
    offsets and the quoted span.
    """

    provenance_id: str
    chunk_id: str
    source_id: str
    source_title: str
    source_kind: SourceKind
    version_number: int
    page: int | None
    start_offset: int | None
    end_offset: int | None
    excerpt: str
    information_status: str
