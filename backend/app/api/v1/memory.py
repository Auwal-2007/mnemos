"""Verification, correction and conflict endpoints (Phase 3C).

Surface
-------
``POST /memory/answers/{answer_id}/verify``          verify an answer's claims
``GET  /memory/workspaces/{id}/corrections``         list corrections
``POST /memory/workspaces/{id}/corrections``         propose a correction
``POST /memory/corrections/{id}/review``             approve or reject
``POST /memory/corrections/{id}/apply``              apply an approved correction
``GET  /memory/workspaces/{id}/conflicts``           list conflicts
``POST /memory/workspaces/{id}/conflicts/detect``    detect conflicts among passages
``POST /memory/conflicts/{id}/resolve``              resolve or dismiss

Separation of duties is enforced in the service and in the database, so a
proposer receives 403 when they try to approve their own correction — the API
does not merely hope the client will not offer the button.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import AuthContextDep, WorkspaceRepoDep, derived_write_client
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.domain.verification import CorrectionStatus, VerificationMethod
from app.infrastructure.completion import chat_provider_from_settings
from app.repositories.conversation_repositories import SupabaseAnswerRepository
from app.repositories.verification_repositories import (
    SupabaseConflictRepository,
    SupabaseCorrectionRepository,
    SupabaseVerificationRepository,
)
from app.services.verification import PassageText, VerificationService

logger = logging.getLogger("mnemos.api.memory")

router = APIRouter(prefix="/memory", tags=["memory"])


# --- schemas -------------------------------------------------------------


class VerificationRequest(BaseModel):
    """Which method to verify with.

    `model_judgement` requires a configured verification model; requesting it
    without one returns 503 rather than silently falling back to lexical.
    """

    method: Literal["lexical_overlap", "model_judgement"] = "lexical_overlap"
    provenance_ids: list[str] = Field(
        default_factory=list,
        description="Passages the answer cited; required to resolve claim evidence.",
    )


class ClaimVerificationResponse(BaseModel):
    claim_id: str
    verdict: str
    method: str
    confidence: float | None = None
    explanation: str


class VerificationResponse(BaseModel):
    answer_id: str
    method: str
    supported: int
    unsupported: int
    unverified: int
    contradicted: int
    total: int
    fully_verified: bool
    reliability: float | None = Field(
        default=None,
        description=(
            "Share of checked claims that were supported. Null when nothing was "
            "checked — 0 would imply every claim failed."
        ),
    )
    claims: list[ClaimVerificationResponse]


class CorrectionResponse(BaseModel):
    id: str
    workspace_id: str
    provenance_id: str
    corrected_text: str
    rationale: str | None = None
    status: str
    proposed_by: str
    reviewed_by: str | None = None
    applied_provenance_id: str | None = None
    is_self_review: bool = False


class CorrectionListResponse(BaseModel):
    items: list[CorrectionResponse]
    total: int


class ProposeCorrectionRequest(BaseModel):
    provenance_id: str = Field(min_length=1)
    corrected_text: str = Field(min_length=1, max_length=20000)
    rationale: str | None = Field(default=None, max_length=2000)


class ReviewCorrectionRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class ApplyCorrectionResponse(BaseModel):
    correction_id: str
    revision_provenance_id: str
    status: str = "applied"


class ConflictResponse(BaseModel):
    id: str
    workspace_id: str
    provenance_a: str
    provenance_b: str
    detected_reason: str
    detection_method: str
    score: float | None = None
    status: str
    resolved_by: str | None = None
    resolution_note: str | None = None


class ConflictListResponse(BaseModel):
    items: list[ConflictResponse]
    total: int


class DetectConflictsRequest(BaseModel):
    provenance_ids: list[str] = Field(min_length=2, max_length=50)
    record: bool = Field(
        default=False, description="Persist detected candidates as conflict records."
    )


class DetectConflictsResponse(BaseModel):
    candidates: list[ConflictResponse]
    recorded_ids: list[str]


class ResolveConflictRequest(BaseModel):
    dismiss: bool = False
    note: str | None = Field(default=None, max_length=2000)


# --- service graph -------------------------------------------------------


def _service(
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Settings,
) -> VerificationService:
    write_client = derived_write_client(context)
    provider = None
    if settings.is_openrouter_configured and settings.model_for_role("verification"):
        provider = chat_provider_from_settings(settings, role="verification")
    return VerificationService(
        workspaces=workspaces,
        store=SupabaseVerificationRepository(context.client, write_client),
        corrections=SupabaseCorrectionRepository(context.client, write_client),
        conflicts=SupabaseConflictRepository(context.client, write_client),
        provider=provider,
    )


# --- verification --------------------------------------------------------


@router.post(
    "/answers/{answer_id}/verify",
    summary="Verify an answer's claims against the evidence they cite",
)
async def verify_answer(
    answer_id: Annotated[str, Path(description="Answer id")],
    body: VerificationRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> VerificationResponse:
    """Check each claim and record a verdict.

    A verdict of `unverified` means the claim could not be checked, which is
    deliberately distinct from `unsupported` (checked and found wanting).
    """
    method = VerificationMethod(body.method)
    write_client = derived_write_client(context)
    answers = SupabaseAnswerRepository(context.client, write_client)
    record = answers.get_answer(answer_id)
    if record is None:
        raise NotFoundError(message="Answer not found.")

    workspace_id = str(record["workspace_id"])
    claims = answers.list_claims(answer_id)
    # The caller supplies the provenance ids it displayed. Reading the text back
    # through RLS means a claim is checked against the same passage the user saw.
    context_map = {
        citation.provenance_id for claim in claims for citation in claim.citations
    } & set(body.provenance_ids or [])
    service = _service(context, workspaces, settings)
    texts = service._conflicts.passages_for(workspace_id, sorted(context_map))
    evidence = {
        pid: PassageText(provenance_id=pid, chunk_id=pid, text=text) for pid, text in texts.items()
    }

    result = await service.verify_answer(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        answer_id=answer_id,
        evidence=evidence,
        method=method,
    )
    return VerificationResponse(
        answer_id=result.answer_id,
        method=result.method.value,
        supported=result.supported,
        unsupported=result.unsupported,
        unverified=result.unverified,
        contradicted=result.contradicted,
        total=result.total,
        fully_verified=result.fully_verified,
        reliability=result.reliability,
        claims=[
            ClaimVerificationResponse(
                claim_id=verdict.claim_id,
                verdict=verdict.verdict,
                method=verdict.method.value,
                confidence=verdict.confidence,
                explanation=verdict.explanation,
            )
            for verdict in result.verifications
        ],
    )


# --- corrections ---------------------------------------------------------


@router.get("/workspaces/{workspace_id}/corrections", summary="List corrections")
async def list_corrections(
    workspace_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CorrectionListResponse:
    rows = _service(context, workspaces, settings).list_corrections(
        workspace_id, context.identity.user_id, status=status
    )
    return CorrectionListResponse(items=[_correction(row) for row in rows[:limit]], total=len(rows))


@router.post("/workspaces/{workspace_id}/corrections", summary="Propose a correction")
async def propose_correction(
    workspace_id: str,
    body: ProposeCorrectionRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CorrectionResponse:
    correction = _service(context, workspaces, settings).propose_correction(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        provenance_id=body.provenance_id,
        corrected_text=body.corrected_text,
        rationale=body.rationale,
    )
    return _correction(correction)


@router.post("/corrections/{correction_id}/review", summary="Approve or reject a correction")
async def review_correction(
    correction_id: str,
    body: ReviewCorrectionRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CorrectionResponse:
    """Approve or reject. The proposer cannot review their own correction."""
    service = _service(context, workspaces, settings)
    existing = service._corrections.get(correction_id)
    if existing is None:
        raise NotFoundError(message="Correction not found.")
    correction = service.review_correction(
        workspace_id=existing.workspace_id,
        user_id=context.identity.user_id,
        correction_id=correction_id,
        approve=body.approve,
        note=body.note,
    )
    return _correction(correction)


@router.post(
    "/corrections/{correction_id}/apply",
    summary="Apply an approved correction, creating a revision",
)
async def apply_correction(
    correction_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApplyCorrectionResponse:
    """Supersede the original passage with a revision of the corrected text.

    The original is never overwritten: earlier citations continue to resolve to
    what they actually said at the time.
    """
    service = _service(context, workspaces, settings)
    existing = service._corrections.get(correction_id)
    if existing is None:
        raise NotFoundError(message="Correction not found.")
    revision = service.apply_correction(
        workspace_id=existing.workspace_id,
        user_id=context.identity.user_id,
        correction_id=correction_id,
    )
    return ApplyCorrectionResponse(
        correction_id=correction_id,
        revision_provenance_id=revision,
        status=CorrectionStatus.APPLIED.value,
    )


# --- conflicts -----------------------------------------------------------


@router.get("/workspaces/{workspace_id}/conflicts", summary="List conflicts")
async def list_conflicts(
    workspace_id: str,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ConflictListResponse:
    rows = _service(context, workspaces, settings).list_conflicts(
        workspace_id, context.identity.user_id, status=status
    )
    return ConflictListResponse(items=[_conflict(row) for row in rows[:limit]], total=len(rows))


@router.post(
    "/workspaces/{workspace_id}/conflicts/detect",
    summary="Detect conflicting passages",
)
async def detect_conflicts(
    workspace_id: str,
    body: DetectConflictsRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DetectConflictsResponse:
    """Look for contradictions among the supplied passages.

    Detection is conservative and records the method and score that produced
    each candidate. Recording is opt-in so a preview never pollutes the audit
    trail.
    """
    service = _service(context, workspaces, settings)
    candidates = service.detect_conflicts(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        provenance_ids=body.provenance_ids,
    )
    recorded: list[str] = []
    if body.record and candidates:
        recorded = service.record_conflicts(
            workspace_id=workspace_id,
            user_id=context.identity.user_id,
            candidates=candidates,
        )
    return DetectConflictsResponse(
        candidates=[
            ConflictResponse(
                id=recorded[index] if index < len(recorded) else "",
                workspace_id=workspace_id,
                provenance_a=candidate.provenance_a,
                provenance_b=candidate.provenance_b,
                detected_reason=candidate.reason,
                detection_method=candidate.method.value,
                score=candidate.score,
                status="open",
            )
            for index, candidate in enumerate(candidates)
        ],
        recorded_ids=recorded,
    )


@router.post("/conflicts/{conflict_id}/resolve", summary="Resolve or dismiss a conflict")
async def resolve_conflict(
    conflict_id: str,
    body: ResolveConflictRequest,
    context: AuthContextDep,
    workspaces: WorkspaceRepoDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    service = _service(context, workspaces, settings)
    # The workspace comes from the row itself (RLS-scoped read), never from the
    # request, so a caller cannot resolve a conflict in a workspace they named.
    record = service._conflicts.get(conflict_id)
    if record is None:
        raise NotFoundError(message="Conflict not found.")
    workspace_id = str(record["workspace_id"])
    service.resolve_conflict(
        workspace_id=workspace_id,
        user_id=context.identity.user_id,
        conflict_id=conflict_id,
        note=body.note,
        dismiss=body.dismiss,
    )
    return {
        "id": conflict_id,
        "status": "dismissed" if body.dismiss else "resolved_by_user",
    }


# --- mappers -------------------------------------------------------------


def _correction(row: Any) -> CorrectionResponse:
    return CorrectionResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        provenance_id=row.provenance_id,
        corrected_text=row.corrected_text,
        rationale=row.rationale,
        status=row.status.value,
        proposed_by=row.proposed_by,
        reviewed_by=row.reviewed_by,
        applied_provenance_id=row.applied_provenance_id,
        is_self_review=row.is_self_review,
    )


def _conflict(row: dict[str, Any]) -> ConflictResponse:
    return ConflictResponse(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        provenance_a=str(row["provenance_a"]),
        provenance_b=str(row["provenance_b"]),
        detected_reason=str(row["detected_reason"]),
        detection_method=str(row["detection_method"]),
        score=row.get("score"),
        status=str(row["status"]),
        resolved_by=row.get("resolved_by"),
        resolution_note=row.get("resolution_note"),
    )
