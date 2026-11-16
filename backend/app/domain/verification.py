"""Verification, correction and conflict domain models (Phase 3C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class VerificationMethod(StrEnum):
    """How a verdict was reached. Recorded so nobody mistakes a heuristic for proof."""

    LEXICAL_OVERLAP = "lexical_overlap"
    MODEL_JUDGEMENT = "model_judgement"
    MANUAL = "manual"


class CorrectionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED_BY_USER = "resolved_by_user"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    """The outcome of checking one claim against its cited evidence."""

    claim_id: str
    verdict: str  # ClaimSupport value
    method: VerificationMethod
    confidence: float | None
    explanation: str
    supporting_chunk_ids: list[str] = field(default_factory=list)
    contradicted_by_chunk_ids: list[str] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        return self.verdict in {"supported", "partially_supported"}


@dataclass(frozen=True, slots=True)
class AnswerVerification:
    """A whole answer's verification result.

    `unverified_claims` is reported separately from unsupported ones because a
    claim nobody checked is not evidence of a problem — presenting them as equal
    would overstate the system's confidence in its own audit.
    """

    answer_id: str
    verifications: list[ClaimVerdict]
    method: VerificationMethod
    supported: int
    unsupported: int
    unverified: int
    contradicted: int

    @property
    def total(self) -> int:
        return len(self.verifications)

    @property
    def fully_verified(self) -> bool:
        """True when every claim was checked and none failed."""
        return self.unverified == 0 and self.unsupported == 0 and self.contradicted == 0

    @property
    def reliability(self) -> float | None:
        """Share of checked claims that were supported.

        None when nothing was checked: reporting 0% would imply every claim
        failed, and 100% would imply success.
        """
        checked = self.supported + self.unsupported + self.contradicted
        if checked == 0:
            return None
        return self.supported / checked


@dataclass(frozen=True, slots=True)
class Correction:
    """A proposed correction to a passage (FR-009)."""

    id: str
    workspace_id: str
    provenance_id: str
    corrected_text: str
    rationale: str | None
    status: CorrectionStatus
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    applied_provenance_id: str | None
    created_at: datetime

    @property
    def is_pending(self) -> bool:
        return self.status is CorrectionStatus.PROPOSED

    @property
    def is_self_review(self) -> bool:
        return self.reviewed_by is not None and self.reviewed_by == self.proposed_by


@dataclass(frozen=True, slots=True)
class Conflict:
    """Two passages that assert incompatible things (FR-008)."""

    id: str
    workspace_id: str
    provenance_a: str
    provenance_b: str
    detected_reason: str
    detection_method: VerificationMethod
    score: float | None
    status: ConflictStatus
    resolved_by: str | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConflictCandidate:
    """A detected potential conflict, before it is persisted."""

    provenance_a: str
    provenance_b: str
    reason: str
    method: VerificationMethod
    score: float | None
