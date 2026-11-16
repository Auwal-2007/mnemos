"""Multi-agent orchestration endpoints (Phase 3D).

``POST /agents/workspaces/{id}/ask``       ask via the agent plan
``GET  /agents/orchestrations/{id}``       read one trace
``GET  /agents/workspaces/{id}/orchestrations``  recent runs

The trace is returned with every answer so a reader can see which agents ran,
what each concluded and whether anything was skipped. An answer produced without
a critic is reported as degraded with the reason, never as fully checked.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import AuthContextDep, WorkspaceRepoDep, derived_write_client
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.domain.verification import VerificationMethod
from app.infrastructure.completion import chat_provider_from_settings
from app.infrastructure.embeddings import embedding_provider_from_settings
from app.repositories.agent_repositories import SupabaseTraceRepository
from app.repositories.conversation_repositories import (
    SupabaseAnswerRepository,
    SupabaseConversationRepository,
)
from app.repositories.knowledge_repositories import SupabaseRetrievalRepository
from app.repositories.verification_repositories import (
    SupabaseConflictRepository,
    SupabaseCorrectionRepository,
    SupabaseVerificationRepository,
)
from app.schemas.conversation import (
    AnswerResponse,
    CitationResponse,
    ClaimResponse,
    ExecutionSummary,
)
from app.services.conversation_service import ConversationService
from app.services.generation import GenerationOptions, GenerationService
from app.services.orchestration import OrchestrationService
from app.services.retrieval import RetrievalOptions, RetrievalService
from app.services.verification import VerificationService

logger = logging.getLogger("mnemos.api.agents")

router = APIRouter(prefix="/agents", tags=["agents"])


# --- schemas -------------------------------------------------------------


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    verify: bool = Field(
        default=True,
        description=(
            "Run the critic. If no verification model is configured this is "
            "recorded as skipped, not as a successful check."
        ),
    )
    method: Literal["lexical_overlap", "model_judgement"] = "lexical_overlap"
    max_tokens: int = Field(default=1200, ge=64, le=4000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    candidate_count: int = Field(default=12, ge=4, le=50)
    limit: int = Field(default=6, ge=1, le=20)


class AgentStepResponse(BaseModel):
    capability: str
    status: str
    detail: dict[str, Any]
    latency_ms: int | None = None


class AgentRunResponse(BaseModel):
    role: str
    status: str
    latency_ms: int | None = None
    step_count: int
    error_code: str | None = None
    output_summary: dict[str, Any]
    steps: list[AgentStepResponse]


class VerificationCounts(BaseModel):
    supported: int
    unsupported: int
    unverified: int
    contradicted: int
    reliability: float | None = None
    method: str


class AgentAskResponse(BaseModel):
    conversation_id: str
    answer: AnswerResponse
    execution: ExecutionSummary
    agent_trace: list[AgentRunResponse]
    degraded: bool
    verification: VerificationCounts | None = None
    verification_skipped_reason: str | None = None


class OrchestrationSummary(BaseModel):
    id: str
    workspace_id: str
    conversation_id: str | None = None
    answer_id: str | None = None
    question: str
    plan: list[str]
    status: str
    started_at: str
    completed_at: str | None = None
    total_latency_ms: int | None = None
    total_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestrationDetail(OrchestrationSummary):
    agent_trace: list[AgentRunResponse]


class OrchestrationListResponse(BaseModel):
    items: list[OrchestrationSummary]
    total: int


# --- wiring --------------------------------------------------------------


def _service(
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Settings,
) -> OrchestrationService:
    """Build the agent graph for one request.

    Each agent is given only the services its capabilities allow. The critic gets
    the verification service, never the generation service; the analyst gets the
    conversation service, never a way to verify itself.
    """
    read_client = context.client
    write_client = derived_write_client(context)

    retrieval = RetrievalService(
        workspaces=workspaces,
        search=SupabaseRetrievalRepository(read_client),
        provider=embedding_provider_from_settings(settings)
        if settings.is_embedding_configured
        else None,
    )
    generation_provider = (
        chat_provider_from_settings(settings, role="generation")
        if settings.is_openrouter_configured
        else None
    )
    if generation_provider is None:
        raise NotFoundError(
            message=(
                "Generation is not configured. Set OPENROUTER_API_KEY and a "
                "generation model before asking an agent."
            )
        )
    generation = GenerationService(
        retrieval=retrieval,
        provider=generation_provider,
        store=SupabaseAnswerRepository(read_client, write_client),
    )
    conversations = ConversationService(
        workspaces=workspaces,
        conversations=SupabaseConversationRepository(read_client, write_client),
        generation=generation,
    )
    verification_provider = None
    if settings.is_openrouter_configured and settings.model_for_role("verification"):
        verification_provider = chat_provider_from_settings(settings, role="verification")
    verification = VerificationService(
        workspaces=workspaces,
        store=SupabaseVerificationRepository(read_client, write_client),
        corrections=SupabaseCorrectionRepository(read_client, write_client),
        conflicts=SupabaseConflictRepository(read_client, write_client),
        provider=verification_provider,
    )
    return OrchestrationService(
        workspaces=workspaces,
        conversations=conversations,
        generation=generation,
        verification=verification,
        traces=SupabaseTraceRepository(read_client, write_client),
        verifier_available=verification_provider is not None,
    )


def _traces(context: AuthContextDep) -> SupabaseTraceRepository:
    return SupabaseTraceRepository(context.client, derived_write_client(context))


# --- endpoints -----------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/ask",
    summary="Ask a question answered by the agent plan",
)
async def ask(
    workspace_id: str,
    body: AgentAskRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentAskResponse:
    result = await _service(context, workspaces, settings).ask(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        question=body.question,
        conversation_id=body.conversation_id,
        options=GenerationOptions(
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            retrieval=RetrievalOptions(limit=body.limit, candidate_count=body.candidate_count),
        ),
        verify=body.verify,
        method=VerificationMethod(body.method),
    )
    verification = None
    if result.verification is not None:
        verification = VerificationCounts(
            supported=result.verification.supported,
            unsupported=result.verification.unsupported,
            unverified=result.verification.unverified,
            contradicted=result.verification.contradicted,
            reliability=result.verification.reliability,
            method=result.verification.method.value,
        )
    return AgentAskResponse(
        conversation_id=result.conversation_id,
        answer=_answer(result),
        execution=_execution(result),
        agent_trace=[_run(run) for run in result.run.trace],
        degraded=result.degraded,
        verification=verification,
        verification_skipped_reason=result.verification_skipped_reason,
    )


@router.get("/orchestrations/{orchestration_id}", summary="Read an orchestration trace")
async def get_orchestration(
    orchestration_id: Annotated[str, Path(description="Orchestration id")],
    context: AuthContextDep,
) -> OrchestrationDetail:
    repository = _traces(context)
    record = repository.get_orchestration(orchestration_id)
    if record is None:
        raise NotFoundError(message="Orchestration not found.")
    rows = repository.trace(orchestration_id)
    return OrchestrationDetail(
        **_summary(record).model_dump(),
        agent_trace=_runs_from_rows(rows),
    )


@router.get(
    "/workspaces/{workspace_id}/orchestrations",
    summary="List recent orchestration runs",
)
async def list_orchestrations(
    workspace_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrchestrationListResponse:
    # Membership is checked through the workspace repository so a non-member
    # gets 403 rather than an empty list they might read as "no runs".
    workspace = workspaces.get(workspace_id)
    if workspace is None:
        raise NotFoundError(message="Workspace not found.")
    rows = _traces(context).list_orchestrations(workspace_id, limit=limit)
    return OrchestrationListResponse(items=[_summary(row) for row in rows], total=len(rows))


# --- mappers -------------------------------------------------------------


def _citations(outcome: Any) -> list[CitationResponse]:
    by_id = {passage.provenance_id: passage for passage in outcome.passages}
    citations: list[CitationResponse] = []
    for claim in outcome.claims:
        for provenance_id in outcome.citations_by_claim.get(claim.index, []):
            passage = by_id.get(provenance_id)
            if passage is None:
                continue
            citations.append(
                CitationResponse(
                    provenance_id=passage.provenance_id,
                    chunk_id=passage.chunk_id,
                    source_id=passage.source_id,
                    source_title=passage.source_title,
                    source_kind=passage.source_kind.value,
                    version_number=passage.version_number,
                    page=passage.page,
                    start_offset=passage.start_offset,
                    end_offset=passage.end_offset,
                    excerpt=passage.content[:280],
                    information_status=passage.information_status.value,
                )
            )
    return citations


def _answer(result: Any) -> AnswerResponse:
    outcome = result.outcome
    citations = _citations(outcome)
    by_provenance = {citation.provenance_id: citation for citation in citations}
    claims = [
        ClaimResponse(
            text=claim.text,
            citations=[
                by_provenance[provenance_id]
                for provenance_id in outcome.citations_by_claim.get(claim.index, [])
                if provenance_id in by_provenance
            ],
        )
        for claim in outcome.claims
    ]
    return AnswerResponse(
        answer_id=outcome.answer_id,
        status=outcome.status.value,
        content=outcome.content,
        abstention_reason=outcome.abstention_reason,
        claims=claims,
        evidence_considered=outcome.evidence_considered,
        evidence_cited=outcome.evidence_cited,
        evidence=citations,
        degraded_reason=result.verification_skipped_reason if result.degraded else None,
        execution=_execution(result),
    )


def _execution(result: Any) -> ExecutionSummary:
    execution = result.execution
    return ExecutionSummary(
        id=execution.id,
        agent_role=execution.agent_role.value,
        model_id=execution.model_id,
        status=execution.status.value,
        latency_ms=execution.latency_ms,
        prompt_tokens=execution.prompt_tokens,
        completion_tokens=execution.completion_tokens,
        total_tokens=execution.total_tokens,
    )


def _run(run: dict[str, Any]) -> AgentRunResponse:
    return AgentRunResponse(
        role=str(run["role"]),
        status=str(run["status"]),
        latency_ms=run.get("latency_ms"),
        step_count=int(run.get("step_count") or 0),
        error_code=run.get("error_code"),
        output_summary=run.get("output_summary") or {},
        steps=[
            AgentStepResponse(
                capability=str(step["capability"]),
                status=str(step["status"]),
                detail=step.get("detail") or {},
                latency_ms=step.get("latency_ms"),
            )
            for step in run.get("steps") or []
        ],
    )


def _runs_from_rows(rows: list[dict[str, Any]]) -> list[AgentRunResponse]:
    """Collapse flattened trace rows back into per-agent runs."""
    by_run: dict[str, AgentRunResponse] = {}
    for row in rows:
        run_id = str(row["agent_run_id"])
        run = by_run.get(run_id)
        if run is None:
            run = AgentRunResponse(
                role=str(row["role"]),
                status=str(row["run_status"]),
                latency_ms=row.get("latency_ms"),
                step_count=0,
                output_summary={},
                steps=[],
            )
            by_run[run_id] = run
        if row.get("capability") is not None:
            run.steps.append(
                AgentStepResponse(
                    capability=str(row["capability"]),
                    status=str(row["step_status"]),
                    detail=row.get("detail") or {},
                )
            )
    for run in by_run.values():
        run.step_count = len(run.steps)
    return list(by_run.values())


def _summary(row: dict[str, Any]) -> OrchestrationSummary:
    return OrchestrationSummary(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        conversation_id=row.get("conversation_id"),
        answer_id=row.get("answer_id"),
        question=str(row["question"]),
        plan=list(row.get("plan") or []),
        status=str(row["status"]),
        started_at=str(row["started_at"]),
        completed_at=row.get("completed_at"),
        total_latency_ms=row.get("total_latency_ms"),
        total_tokens=row.get("total_tokens"),
        metadata=row.get("metadata") or {},
    )
