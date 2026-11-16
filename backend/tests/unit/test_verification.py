"""Verification, correction and conflict tests (Phase 3C).

The properties being protected:

* an unchecked claim is reported as unverified, never as supported or failed;
* reliability is None when nothing was checked, because 0% would imply every
  claim failed and 100% would imply success;
* a model that misbehaves leaves claims unverified rather than assuming support;
* a correction cannot be self-reviewed, and applying it is not something the
  service can be talked into without an approval;
* conflict detection is conservative and records why it fired.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.domain.conversation import CitationDraft, Claim, ClaimSupport
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.domain.verification import (
    AnswerVerification,
    ClaimVerdict,
    ConflictCandidate,
    Correction,
    CorrectionStatus,
    VerificationMethod,
)
from app.infrastructure.completion import (
    ChatMessage,
    CompletionError,
    CompletionResult,
    CompletionUsage,
)
from app.services.verification import (
    SUPPORTED_AT,
    UNSUPPORTED_BELOW,
    PassageText,
    VerificationService,
    _conflict_between,
    lexical_support,
    normalise_terms,
)

WS = "33333333-3333-4333-8333-333333333333"
USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
ANSWER = "55555555-5555-4555-8555-555555555555"
PROV_A = "aaaaaaaa-0000-4000-8000-000000000001"
PROV_B = "bbbbbbbb-0000-4000-8000-000000000002"
STAMP = dt.datetime(2026, 11, 15, tzinfo=dt.UTC)


# --- fakes ---------------------------------------------------------------


class FakeWorkspaces:
    def __init__(self, members: list[WorkspaceMember] | None = None, exists: bool = True) -> None:
        self.members = members if members is not None else [member()]
        self.exists = exists

    def get(self, workspace_id: str) -> Workspace | None:
        if not self.exists:
            return None
        return Workspace(
            id=workspace_id,
            owner_id=USER,
            name="R",
            slug="r",
            description=None,
            created_at=STAMP,
            updated_at=STAMP,
        )

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return self.members


def member(user_id: str = USER, role: WorkspaceRole = WorkspaceRole.OWNER) -> WorkspaceMember:
    return WorkspaceMember(workspace_id=WS, user_id=user_id, role=role, created_at=STAMP)


@dataclass
class FakeVerificationStore:
    claims: list[Claim] = field(default_factory=list)
    saved: list[ClaimVerdict] = field(default_factory=list)
    support_updates: list[tuple[str, ClaimSupport]] = field(default_factory=list)

    def claims_for_answer(self, answer_id: str) -> list[Claim]:
        return self.claims

    def save_verification(self, **kwargs: Any) -> None:
        self.saved.append(kwargs["verdict"])

    def update_claim_support(
        self, claim_id: str, *, support: ClaimSupport, note: str | None
    ) -> None:
        self.support_updates.append((claim_id, support))


@dataclass
class FakeCorrectionStore:
    corrections: dict[str, Correction] = field(default_factory=dict)
    applied: list[tuple[str, str]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Correction:
        correction = Correction(
            id=f"corr-{len(self.corrections) + 1}",
            workspace_id=kwargs["workspace_id"],
            provenance_id=kwargs["provenance_id"],
            corrected_text=kwargs["corrected_text"],
            rationale=kwargs.get("rationale"),
            status=CorrectionStatus.PROPOSED,
            proposed_by=kwargs["proposed_by"],
            reviewed_by=None,
            reviewed_at=None,
            applied_provenance_id=None,
            created_at=STAMP,
        )
        self.corrections[correction.id] = correction
        return correction

    def get(self, correction_id: str) -> Correction | None:
        return self.corrections.get(correction_id)

    def list_for_workspace(
        self, workspace_id: str, *, status: str | None = None, limit: int = 50
    ) -> list[Correction]:
        return list(self.corrections.values())

    def review(
        self, correction_id: str, *, status: CorrectionStatus, reviewed_by: str
    ) -> Correction:
        existing = self.corrections[correction_id]
        updated = Correction(
            id=existing.id,
            workspace_id=existing.workspace_id,
            provenance_id=existing.provenance_id,
            corrected_text=existing.corrected_text,
            rationale=existing.rationale,
            status=status,
            proposed_by=existing.proposed_by,
            reviewed_by=reviewed_by,
            reviewed_at=STAMP,
            applied_provenance_id=None,
            created_at=existing.created_at,
        )
        self.corrections[correction_id] = updated
        return updated

    def apply(self, correction_id: str, *, actor: str) -> str:
        self.applied.append((correction_id, actor))
        return "revision-provenance-id"


@dataclass
class FakeConflictStore:
    recorded: list[ConflictCandidate] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    resolutions: list[dict[str, Any]] = field(default_factory=list)

    def record(self, *, workspace_id: str, candidate: ConflictCandidate) -> str:
        self.recorded.append(candidate)
        return f"conflict-{len(self.recorded)}"

    def list_for_workspace(
        self, workspace_id: str, *, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return []

    def resolve(self, conflict_id: str, *, status: str, resolved_by: str, note: str | None) -> None:
        self.resolutions.append(
            {"id": conflict_id, "status": status, "by": resolved_by, "note": note}
        )

    def passages_for(self, workspace_id: str, provenance_ids: list[str]) -> dict[str, str]:
        return {pid: self.texts[pid] for pid in provenance_ids if pid in self.texts}


class FakeProvider:
    model_id = "fake/verifier"

    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> CompletionResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.content is not None
        return CompletionResult(
            content=self.content,
            model_requested=self.model_id,
            model_reported=self.model_id,
            usage=CompletionUsage(1, 1, 2),
            latency_ms=1,
        )


def claim(text: str, citations: list[str] | None = None) -> Claim:
    return Claim(
        id="claim-1",
        answer_id=ANSWER,
        claim_index=0,
        text=text,
        support=ClaimSupport.UNVERIFIED,
        verification_note=None,
        citations=[
            CitationDraft(provenance_id=pid, quoted_text=None, relevance=None)
            for pid in (citations if citations is not None else [PROV_A])
        ],
    )


def service(
    *,
    claims: list[Claim] | None = None,
    members: list[WorkspaceMember] | None = None,
    provider: FakeProvider | None = None,
    corrections: FakeCorrectionStore | None = None,
    conflicts: FakeConflictStore | None = None,
) -> tuple[VerificationService, FakeVerificationStore, FakeCorrectionStore, FakeConflictStore]:
    store = FakeVerificationStore(
        claims=claims if claims is not None else [claim("A passport is required.")]
    )
    correction_store = corrections or FakeCorrectionStore()
    conflict_store = conflicts or FakeConflictStore()
    return (
        VerificationService(
            workspaces=FakeWorkspaces(members),  # type: ignore[arg-type]
            store=store,
            corrections=correction_store,
            conflicts=conflict_store,
            provider=provider,  # type: ignore[arg-type]
        ),
        store,
        correction_store,
        conflict_store,
    )


EVIDENCE = {
    PROV_A: PassageText(
        provenance_id=PROV_A,
        chunk_id="chunk-a",
        text="A passport is required for international travel.",
    )
}


# --- lexical scoring -----------------------------------------------------


def test_normalise_terms_drops_stopwords_and_punctuation() -> None:
    assert normalise_terms("The PASSPORT, is required!") == {"passport", "required"}


def test_identical_text_scores_one() -> None:
    score, contributors = lexical_support(
        "A passport is required for international travel.", list(EVIDENCE.values())
    )
    assert score == 1.0
    assert contributors == ["chunk-a"]


def test_unrelated_text_scores_zero() -> None:
    score, contributors = lexical_support("Bananas taste better green.", list(EVIDENCE.values()))
    assert score == 0.0
    assert contributors == []


def test_claim_with_no_content_words_scores_zero() -> None:
    score, _ = lexical_support("the a of", list(EVIDENCE.values()))
    assert score == 0.0


# --- verification --------------------------------------------------------


async def test_supported_claim_is_recorded_as_supported() -> None:
    svc, store, _, _ = service()
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE
    )
    assert result.supported == 1
    assert result.unsupported == 0
    assert store.support_updates[0][1] is ClaimSupport.SUPPORTED


async def test_unsupported_claim_is_reported_as_unsupported_not_unverified() -> None:
    svc, store, _, _ = service(claims=[claim("Bananas are the only fruit.")])
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE
    )
    assert result.unsupported == 1
    assert result.unverified == 0
    assert store.support_updates[0][1] is ClaimSupport.UNSUPPORTED


async def test_claim_with_no_resolvable_evidence_stays_unverified() -> None:
    """A claim whose citation cannot be resolved must not be called supported."""
    svc, store, _, _ = service(claims=[claim("Anything at all.", citations=[PROV_B])])
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE
    )
    assert result.unverified == 1
    assert result.supported == 0
    assert store.saved[0].verdict == "unverified"


async def test_unverified_claims_have_no_verdict_support() -> None:
    svc, _, _, _ = service(claims=[claim("x", citations=[])])
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE
    )
    assert result.verifications[0].verdict == "unverified"


async def test_reliability_is_none_when_nothing_was_checked() -> None:
    """0% would imply every claim failed and 100% would imply success."""
    verification = AnswerVerification(
        answer_id=ANSWER,
        verifications=[],
        method=VerificationMethod.LEXICAL_OVERLAP,
        supported=0,
        unsupported=0,
        unverified=0,
        contradicted=0,
    )
    assert verification.reliability is None


async def test_reliability_is_the_share_of_checked_claims_supported() -> None:
    svc, _, _, _ = service(claims=[claim("A passport is required."), claim("Bananas are fruit.")])
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE
    )
    assert result.reliability == pytest.approx(0.5)


async def test_partial_overlap_is_partially_supported() -> None:
    """A claim that is half in its evidence is not called fully supported."""
    evidence = {
        PROV_A: PassageText(
            provenance_id=PROV_A,
            chunk_id="c",
            text="A passport is required for international travel to some countries.",
        )
    }
    # Claim terms: passport, required, international, travel, antarctica (5).
    # Evidence covers 4 of them, so the score is 0.8 — supported, not partial.
    # Two absent terms are needed to land in the partial band.
    svc, store, _, _ = service(
        claims=[claim("A passport is required for international travel to Antarctica and Mars.")]
    )
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=evidence
    )
    verdict = result.verifications[0]
    assert UNSUPPORTED_BELOW <= (verdict.confidence or 0) < SUPPORTED_AT
    assert verdict.verdict == "partially_supported"
    assert store.support_updates[0][1] is ClaimSupport.PARTIALLY_SUPPORTED


async def test_verification_records_its_method() -> None:
    svc, _, _, _ = service()
    result = await svc.verify_answer(
        workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE
    )
    assert result.method is VerificationMethod.LEXICAL_OVERLAP
    assert result.verifications[0].method is VerificationMethod.LEXICAL_OVERLAP


async def test_model_method_is_used_when_a_provider_is_present() -> None:
    provider = FakeProvider(
        json.dumps({"verdict": "supported", "confidence": 0.9, "explanation": "It says so."})
    )
    svc, store, _, _ = service(provider=provider)
    result = await svc.verify_answer(
        workspace_id=WS,
        user_id=USER,
        answer_id=ANSWER,
        evidence=EVIDENCE,
        method=VerificationMethod.MODEL_JUDGEMENT,
    )
    assert provider.calls == 1
    assert result.method is VerificationMethod.MODEL_JUDGEMENT
    assert store.saved[0].verdict == "supported"


async def test_model_can_find_a_contradiction_the_lexical_method_cannot() -> None:
    provider = FakeProvider(
        json.dumps(
            {
                "verdict": "contradicted",
                "confidence": 0.8,
                "explanation": "The evidence says the opposite.",
            }
        )
    )
    svc, _, _, _ = service(provider=provider, claims=[claim("A passport is never required.")])
    result = await svc.verify_answer(
        workspace_id=WS,
        user_id=USER,
        answer_id=ANSWER,
        evidence=EVIDENCE,
        method=VerificationMethod.MODEL_JUDGEMENT,
    )
    assert result.contradicted == 1
    assert result.fully_verified is False


async def test_model_failure_leaves_claims_unverified_rather_than_supported() -> None:
    """Fail closed: an uncheckable claim must not look checked."""
    provider = FakeProvider(error=CompletionError(message="upstream down"))
    svc, store, _, _ = service(provider=provider)
    result = await svc.verify_answer(
        workspace_id=WS,
        user_id=USER,
        answer_id=ANSWER,
        evidence=EVIDENCE,
        method=VerificationMethod.MODEL_JUDGEMENT,
    )
    assert result.unverified == 1
    assert result.supported == 0
    assert store.saved[0].verdict == "unverified"


async def test_unusable_model_output_leaves_claims_unverified() -> None:
    provider = FakeProvider("not json at all")
    svc, _, _, _ = service(provider=provider)
    result = await svc.verify_answer(
        workspace_id=WS,
        user_id=USER,
        answer_id=ANSWER,
        evidence=EVIDENCE,
        method=VerificationMethod.MODEL_JUDGEMENT,
    )
    assert result.unverified == 1


async def test_non_member_cannot_verify() -> None:
    svc, _, _, _ = service(members=[member(OTHER)])
    with pytest.raises(ForbiddenError):
        await svc.verify_answer(workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE)


async def test_answer_with_no_claims_is_not_found() -> None:
    svc, _, _, _ = service(claims=[])
    with pytest.raises(NotFoundError):
        await svc.verify_answer(workspace_id=WS, user_id=USER, answer_id=ANSWER, evidence=EVIDENCE)


# --- corrections ---------------------------------------------------------


def test_a_contributor_can_propose_a_correction() -> None:
    svc, _, _, _ = service()
    correction = svc.propose_correction(
        workspace_id=WS,
        user_id=USER,
        provenance_id=PROV_A,
        corrected_text="  A passport is required.  ",
        rationale="Simplified.",
    )
    assert correction.corrected_text == "A passport is required."
    assert correction.status is CorrectionStatus.PROPOSED


def test_empty_correction_is_rejected() -> None:
    svc, _, _, _ = service()
    with pytest.raises(ValidationError):
        svc.propose_correction(
            workspace_id=WS, user_id=USER, provenance_id=PROV_A, corrected_text="   "
        )


def test_a_viewer_cannot_propose_a_correction() -> None:
    svc, _, _, _ = service(members=[member(USER, WorkspaceRole.VIEWER)])
    with pytest.raises(ForbiddenError):
        svc.propose_correction(
            workspace_id=WS, user_id=USER, provenance_id=PROV_A, corrected_text="x"
        )


def test_proposer_cannot_review_their_own_correction() -> None:
    """Separation of duties, enforced before the database has to."""
    svc, _, _, _ = service()
    correction = svc.propose_correction(
        workspace_id=WS, user_id=USER, provenance_id=PROV_A, corrected_text="New."
    )
    with pytest.raises(ForbiddenError) as excinfo:
        svc.review_correction(
            workspace_id=WS, user_id=USER, correction_id=correction.id, approve=True
        )
    assert "other than the person" in str(excinfo.value)


def test_a_different_editor_can_approve() -> None:
    svc, _, _, _ = service(members=[member(USER), member(OTHER, WorkspaceRole.EDITOR)])
    correction = svc.propose_correction(
        workspace_id=WS, user_id=OTHER, provenance_id=PROV_A, corrected_text="New."
    )
    approved = svc.review_correction(
        workspace_id=WS, user_id=USER, correction_id=correction.id, approve=True
    )
    assert approved.status is CorrectionStatus.APPROVED
    assert approved.reviewed_by == USER


def test_reviewing_twice_is_refused() -> None:
    svc, _, _, _ = service(members=[member(USER), member(OTHER, WorkspaceRole.EDITOR)])
    correction = svc.propose_correction(
        workspace_id=WS, user_id=OTHER, provenance_id=PROV_A, corrected_text="New."
    )
    svc.review_correction(workspace_id=WS, user_id=USER, correction_id=correction.id, approve=True)
    with pytest.raises(ValidationError):
        svc.review_correction(
            workspace_id=WS, user_id=USER, correction_id=correction.id, approve=True
        )


def test_an_unapproved_correction_cannot_be_applied() -> None:
    svc, _, corrections, _ = service()
    correction = svc.propose_correction(
        workspace_id=WS, user_id=USER, provenance_id=PROV_A, corrected_text="New."
    )
    with pytest.raises(ValidationError):
        svc.apply_correction(workspace_id=WS, user_id=USER, correction_id=correction.id)
    assert corrections.applied == []


def test_a_rejected_correction_cannot_be_applied() -> None:
    svc, _, _, _ = service(members=[member(USER), member(OTHER, WorkspaceRole.EDITOR)])
    correction = svc.propose_correction(
        workspace_id=WS, user_id=OTHER, provenance_id=PROV_A, corrected_text="New."
    )
    svc.review_correction(workspace_id=WS, user_id=USER, correction_id=correction.id, approve=False)
    with pytest.raises(ValidationError):
        svc.apply_correction(workspace_id=WS, user_id=USER, correction_id=correction.id)


def test_an_approved_correction_can_be_applied_and_reports_the_revision() -> None:
    svc, _, corrections, _ = service(members=[member(USER), member(OTHER, WorkspaceRole.EDITOR)])
    correction = svc.propose_correction(
        workspace_id=WS, user_id=OTHER, provenance_id=PROV_A, corrected_text="New."
    )
    svc.review_correction(workspace_id=WS, user_id=USER, correction_id=correction.id, approve=True)
    revision = svc.apply_correction(workspace_id=WS, user_id=USER, correction_id=correction.id)
    assert revision == "revision-provenance-id"
    assert corrections.applied == [(correction.id, USER)]


def test_correction_from_another_workspace_is_not_found() -> None:
    svc, _, _, _ = service()
    with pytest.raises(NotFoundError):
        svc.apply_correction(
            workspace_id="99999999-9999-4999-8999-999999999999",
            user_id=USER,
            correction_id="does-not-exist",
        )


# --- conflicts -----------------------------------------------------------


def test_differing_quantities_for_the_same_unit_are_a_conflict() -> None:
    candidate = _conflict_between(
        PROV_A,
        "A passport must be valid for six months.",
        PROV_B,
        "A passport must be valid for three months.",
    )
    assert candidate is not None
    assert "months" in candidate.reason
    assert candidate.provenance_a == PROV_A


def test_identical_quantities_are_not_a_conflict() -> None:
    assert (
        _conflict_between(
            PROV_A,
            "A passport must be valid for six months.",
            PROV_B,
            "A passport must be valid for 6 months.",
        )
        is None
    )


def test_negation_of_a_shared_subject_is_a_conflict() -> None:
    # The detector needs substantive shared vocabulary before it will consider
    # negation, so this fixture shares four content words.
    candidate = _conflict_between(
        PROV_A,
        "A passport document is required for international travel.",
        PROV_B,
        "A passport document is not required for international travel.",
    )
    assert candidate is not None
    assert "negates" in candidate.reason


def test_unrelated_passages_are_not_a_conflict() -> None:
    assert (
        _conflict_between(
            PROV_A, "A passport must be valid for six months.", PROV_B, "Bananas are yellow."
        )
        is None
    )


def test_conflict_score_is_bounded() -> None:
    candidate = _conflict_between(
        PROV_A,
        "a b c d e f g h i j passport six months required travel",
        PROV_B,
        "a b c d e f g h i j passport three months required travel",
    )
    assert candidate is not None
    assert 0.0 <= (candidate.score or 0) <= 1.0


def test_detect_conflicts_only_considers_supplied_passages() -> None:
    conflicts = FakeConflictStore(texts={PROV_A: "six months", PROV_B: "three months"})
    svc, _, _, _ = service(conflicts=conflicts)
    candidates = svc.detect_conflicts(
        workspace_id=WS, user_id=USER, provenance_ids=[PROV_A, PROV_B]
    )
    # "six months" and "three months" share only two words, so this is *not*
    # flagged: the detector requires substantive shared vocabulary.
    assert candidates == []


def test_detect_conflicts_finds_a_real_pair() -> None:
    conflicts = FakeConflictStore(
        texts={
            PROV_A: "A passport must be valid for six months for travel abroad.",
            PROV_B: "A passport must be valid for three months for travel abroad.",
        }
    )
    svc, _, _, _ = service(conflicts=conflicts)
    candidates = svc.detect_conflicts(
        workspace_id=WS, user_id=USER, provenance_ids=[PROV_A, PROV_B]
    )
    assert len(candidates) == 1
    assert candidates[0].method is VerificationMethod.LEXICAL_OVERLAP


def test_conflicts_are_recorded_canonically() -> None:
    conflicts = FakeConflictStore()
    svc, _, _, _ = service(conflicts=conflicts)
    created = svc.record_conflicts(
        workspace_id=WS,
        user_id=USER,
        candidates=[
            ConflictCandidate(
                provenance_a=PROV_A,
                provenance_b=PROV_B,
                reason="r",
                method=VerificationMethod.LEXICAL_OVERLAP,
                score=0.5,
            )
        ],
    )
    assert created == ["conflict-1"]


def test_a_viewer_cannot_resolve_a_conflict() -> None:
    svc, _, _, _ = service(members=[member(USER, WorkspaceRole.VIEWER)])
    with pytest.raises(ForbiddenError):
        svc.resolve_conflict(workspace_id=WS, user_id=USER, conflict_id="c-1")


def test_resolving_records_who_and_what() -> None:
    conflicts = FakeConflictStore()
    svc, _, _, _ = service(conflicts=conflicts)
    svc.resolve_conflict(
        workspace_id=WS, user_id=USER, conflict_id="c-1", note="Kept the newer policy."
    )
    assert conflicts.resolutions[0]["status"] == "resolved_by_user"
    assert conflicts.resolutions[0]["by"] == USER
