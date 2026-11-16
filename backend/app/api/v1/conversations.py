"""Conversation and grounded-answer endpoints (Phase 3B).

Surface
-------
``GET    /conversations/workspaces/{id}``          list threads
``POST   /conversations/workspaces/{id}``          create a thread
``GET    /conversations/{conversation_id}``        one thread
``GET    /conversations/{conversation_id}/messages``message history
``POST   /conversations/workspaces/{id}/ask``      ask a grounded question
``GET    /conversations/answers/{answer_id}``      answer with claims + evidence

Every route is authenticated, membership-checked and RLS-backed. The answer
endpoint returns claims and their evidence together so the client never has to
reconstruct the link between a sentence and its source.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import AuthContextDep, WorkspaceRepoDep
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.domain.conversation import (
    AgentRole,
    AnswerOutcome,
    AnswerStatus,
    Conversation,
    ExecutionRecord,
    Message,
)
from app.domain.retrieval import RetrievedPassage
from app.infrastructure.completion import chat_provider_from_settings
from app.infrastructure.embeddings import embedding_provider_from_settings
from app.repositories.conversation_repositories import (
    SupabaseAnswerRepository,
    SupabaseConversationRepository,
)
from app.repositories.knowledge_repositories import SupabaseRetrievalRepository
from app.schemas.conversation import (
    AnswerDetailResponse,
    AnswerResponse,
    AskRequest,
    AskResponse,
    CitationResponse,
    ClaimDetailResponse,
    ClaimResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    ExecutionSummary,
    MessageListResponse,
    MessageResponse,
)
from app.services.conversation_service import ConversationService
from app.services.generation import GenerationOptions, GenerationService
from app.services.retrieval import RetrievalOptions, RetrievalService

logger = logging.getLogger("mnemos.api.conversations")

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _service(
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Settings,
) -> ConversationService:
    """Build the service graph for one request.

    The user client reads everything (so RLS decides visibility); the
    service-role client writes only the rows users are not permitted to author.
    Both are created per request from the caller's token, never cached across
    callers.
    """
    from app.api.deps import derived_write_client

    write_client = derived_write_client(context)
    conversations = SupabaseConversationRepository(context.client, write_client)
    answers = SupabaseAnswerRepository(context.client, write_client)

    retrieval = RetrievalService(
        workspaces=workspaces,
        search=SupabaseRetrievalRepository(context.client),
        provider=embedding_provider_from_settings(settings)
        if settings.is_embedding_configured
        else None,
    )
    generation = GenerationService(
        retrieval=retrieval,
        provider=chat_provider_from_settings(settings, role="default"),
        store=answers,
    )
    return ConversationService(
        workspaces=workspaces, conversations=conversations, generation=generation
    )


@router.get(
    "/workspaces/{workspace_id}",
    summary="List conversations in a workspace",
)
async def list_conversations(
    workspace_id: Annotated[str, Path(description="Workspace id")],
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    rows = _service(context, workspaces, settings).list_conversations(
        workspace_id, context.identity.user_id, limit=limit, offset=offset
    )
    return ConversationListResponse(items=[_conversation(row) for row in rows], total=len(rows))


@router.post(
    "/workspaces/{workspace_id}",
    summary="Create a conversation",
)
async def create_conversation(
    workspace_id: Annotated[str, Path(description="Workspace id")],
    body: CreateConversationRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversationResponse:
    role = AgentRole(body.agent_role) if body.agent_role else None
    conversation = _service(context, workspaces, settings).create_conversation(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        title=body.title,
        agent_role=role,
    )
    return _conversation(conversation)


@router.get("/{conversation_id}", summary="Get one conversation")
async def get_conversation(
    conversation_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversationResponse:
    conversation = _service(context, workspaces, settings).get_conversation(
        conversation_id, context.identity.user_id
    )
    return _conversation(conversation)


@router.get("/{conversation_id}/messages", summary="List a conversation's messages")
async def list_messages(
    conversation_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageListResponse:
    messages = _service(context, workspaces, settings).list_messages(
        conversation_id, context.identity.user_id
    )
    return MessageListResponse(items=[_message(row) for row in messages], total=len(messages))


@router.post(
    "/workspaces/{workspace_id}/ask",
    summary="Ask a question grounded in the workspace's knowledge",
)
async def ask(
    workspace_id: Annotated[str, Path(description="Workspace id")],
    body: AskRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    """Retrieve, generate and persist one grounded answer.

    An abstention is returned as HTTP 200 with ``status="insufficient_evidence"``.
    It is a correct outcome, not an error, and the client must render it as one.
    """
    service = _service(context, workspaces, settings)
    role = AgentRole(body.agent_role) if body.agent_role else None
    result = await service.ask(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        question=body.question,
        conversation_id=body.conversation_id,
        agent_role=role,
        options=GenerationOptions(
            retrieval=RetrievalOptions(limit=body.limit, include_superseded=body.include_superseded)
        ),
    )
    return AskResponse(
        conversation_id=result.conversation_id,
        question=_message(result.question_message),
        message=_message(result.answer_message),
        answer=_answer(result.answer, result.execution),
    )


@router.get(
    "/answers/{answer_id}",
    summary="Read an answer with its claims and evidence",
)
async def get_answer(
    answer_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnswerDetailResponse:
    """Return the answer, each claim's verification state and its citations."""
    from app.api.deps import derived_write_client

    write_client = derived_write_client(context)
    answers = SupabaseAnswerRepository(context.client, write_client)
    record = answers.get_answer(answer_id)
    if record is None:
        raise NotFoundError(message="Answer not found.")

    conversation_id = str(record["conversation_id"])
    conversations = SupabaseConversationRepository(context.client, write_client)
    conversation = conversations.get(conversation_id)
    if conversation is None:
        raise NotFoundError(message="Answer not found.")
    # Authorizes the read: RLS would already hide it, but a truthful 403 is
    # better than an empty object for a caller outside the workspace.
    _service(context, workspaces, settings).require_member(
        conversation.workspace_id, context.identity.user_id
    )

    claims = answers.list_claims(answer_id)
    citations = {
        citation.provenance_id: CitationResponse(
            provenance_id=citation.provenance_id,
            chunk_id="",
            source_id="",
            source_title="",
            source_kind="document",
            version_number=0,
            excerpt=citation.quoted_text or "",
            information_status="current",
        )
        for claim in claims
        for citation in claim.citations
    }
    answer_payload = AnswerResponse(
        answer_id=answer_id,
        status=AnswerStatus(str(record["status"])).value,
        content=str(record["content"]),
        abstention_reason=record.get("abstention_reason"),
        claims=[
            ClaimResponse(
                text=claim.text,
                citations=[
                    citations[citation.provenance_id]
                    for citation in claim.citations
                    if citation.provenance_id in citations
                ],
            )
            for claim in claims
        ],
        evidence_considered=int(record["evidence_considered"]),
        evidence_cited=int(record["evidence_cited"]),
        evidence=list(citations.values()),
    )
    return AnswerDetailResponse(
        answer=answer_payload,
        claims=[
            ClaimDetailResponse(
                id=claim.id,
                claim_index=claim.claim_index,
                text=claim.text,
                support=claim.support.value,
                verification_note=claim.verification_note,
                citations=[],
            )
            for claim in claims
        ],
        metadata={"conversation_id": conversation_id},
    )


# --- mappers -------------------------------------------------------------


def _conversation(row: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        owner_id=row.owner_id,
        title=row.title,
        agent_role=row.agent_role.value if row.agent_role else None,
        is_archived=row.is_archived,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message(row: Message) -> MessageResponse:
    return MessageResponse(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role.value,
        content=row.content,
        sequence_number=row.sequence_number,
        execution_id=row.execution_id,
        created_at=row.created_at,
    )


def citation(passage: RetrievedPassage) -> CitationResponse:
    return CitationResponse(
        provenance_id=passage.provenance_id,
        chunk_id=passage.chunk_id,
        source_id=passage.source_id,
        source_title=passage.source_title,
        source_kind=passage.source_kind.value,
        version_number=passage.version_number,
        page=passage.page,
        start_offset=passage.start_offset,
        end_offset=passage.end_offset,
        excerpt=passage.content,
        information_status=passage.information_status.value,
    )


def _answer(outcome: AnswerOutcome, execution: ExecutionRecord | None) -> AnswerResponse:
    by_provenance = {passage.provenance_id: citation(passage) for passage in outcome.passages}
    cited = {pid for ids in outcome.citations_by_claim.values() for pid in ids}
    return AnswerResponse(
        answer_id=outcome.answer_id,
        status=outcome.status.value,
        content=outcome.content,
        abstention_reason=outcome.abstention_reason,
        claims=[
            ClaimResponse(
                text=claim.text,
                citations=[
                    by_provenance[cid] for cid in claim.citation_ids if cid in by_provenance
                ],
            )
            for claim in outcome.claims
        ],
        evidence_considered=outcome.evidence_considered,
        evidence_cited=outcome.evidence_cited,
        evidence=[by_provenance[pid] for pid in sorted(cited) if pid in by_provenance],
        execution=ExecutionSummary(
            id=execution.id,
            agent_role=execution.agent_role.value,
            model_id=execution.model_id,
            status=execution.status.value,
            latency_ms=execution.latency_ms,
            prompt_tokens=execution.prompt_tokens,
            completion_tokens=execution.completion_tokens,
            total_tokens=execution.total_tokens,
        )
        if execution
        else None,
    )
