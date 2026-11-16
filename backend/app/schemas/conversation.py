"""Conversation and answer API schemas (Phase 3B)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    id: str
    workspace_id: str
    owner_id: str
    title: str
    agent_role: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CreateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    agent_role: Literal["orchestrator", "researcher", "analyst", "critic"] | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    sequence_number: int
    execution_id: str | None = None
    created_at: datetime


class CitationResponse(BaseModel):
    """A citation the user can check: which passage, and where it came from."""

    provenance_id: str
    chunk_id: str
    source_id: str
    source_title: str
    source_kind: Literal["document", "note"]
    version_number: int
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    excerpt: str = ""
    information_status: str


class ClaimResponse(BaseModel):
    """One statement of the answer, with the citations attached to it.

    `text` is what the user reads; `citations` are what makes it checkable. An
    empty list is reported as empty rather than omitted, because a claim with no
    support is a fact the user needs to see.
    """

    text: str
    citations: list[CitationResponse] = Field(default_factory=list)


class ExecutionSummary(BaseModel):
    """What was executed. Present so the UI can show cost honestly (FR-014)."""

    id: str
    agent_role: str
    model_id: str
    status: str
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class AnswerResponse(BaseModel):
    answer_id: str
    status: Literal["answered", "insufficient_evidence", "refused", "failed"]
    content: str
    abstention_reason: str | None = None
    claims: list[ClaimResponse] = Field(default_factory=list)
    evidence_considered: int
    evidence_cited: int
    #: The passages cited, so the evidence panel needs no second request.
    evidence: list[CitationResponse] = Field(default_factory=list)
    degraded_reason: str | None = None
    execution: ExecutionSummary | None = None


class AskRequest(BaseModel):
    """A question for a workspace.

    `conversation_id` continues an existing thread. When omitted, a new
    conversation is created and its id returned.
    """

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    agent_role: Literal["orchestrator", "researcher", "analyst", "critic"] | None = None
    limit: int = Field(default=8, ge=1, le=50)
    include_superseded: bool = False


class AskResponse(BaseModel):
    conversation_id: str
    question: MessageResponse
    message: MessageResponse
    answer: AnswerResponse


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


class ClaimDetailResponse(BaseModel):
    """A claim with its verification state (Phase 3C fills `support`)."""

    id: str
    claim_index: int
    text: str
    support: Literal[
        "supported", "partially_supported", "unsupported", "contradicted", "unverified"
    ]
    verification_note: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)


class AnswerDetailResponse(BaseModel):
    answer: AnswerResponse
    claims: list[ClaimDetailResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
