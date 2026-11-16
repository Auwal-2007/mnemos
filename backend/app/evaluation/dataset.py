"""Evaluation dataset model (Phase 4A).

Why a hand-built dataset and not "a few questions"
--------------------------------------------------
An evaluation is only worth the precision of its ground truth. Free-form
questions scored by a model would produce a number that measures the judge as
much as the system. Every case here therefore declares its expected outcome in
a form the runner can check mechanically, and the basis for that expectation is
recorded alongside it.

The corpus is synthetic and licensed as such (it is written for this project),
so there is no redistribution question — which matters, because an evaluation
whose documents cannot be shipped cannot be reproduced.

Case categories exist because a single aggregate score hides the failures that
matter most. A system that answers 90% of trivia well and never abstains is
worse than one that scores 75% and abstains correctly when the corpus is silent.
The runner reports every category separately for exactly that reason.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class CaseCategory(StrEnum):
    """What a case is designed to probe.

    These are behavioural categories, not difficulty tiers. Each one maps to a
    specific way the system could be wrong while still *sounding* right.
    """

    #: Answer is present verbatim in one passage.
    FACTUAL = "factual"
    #: Requires combining two or more documents.
    MULTI_SOURCE = "multi_source"
    #: Answer depends on a specific number, date or threshold.
    PRECISION = "precision"
    #: The corpus states a value that was later superseded.
    SUPERSEDED = "superseded"
    #: Two sources genuinely disagree; the system must not silently pick one.
    CONFLICTING = "conflicting"
    #: The corpus is silent. The only correct behaviour is abstention.
    UNANSWERABLE = "unanswerable"
    #: Related material exists but does not answer the question asked.
    NEAR_MISS = "near_miss"
    #: Question is genuinely ambiguous between two readings.
    AMBIGUOUS = "ambiguous"
    #: Correct answer requires the historical (superseded) value.
    HISTORICAL = "historical"


@dataclass(frozen=True, slots=True)
class EvalDocument:
    """One corpus document.

    ``title`` is the identity used by ground truth, not the filename: a case
    asserts "the answer is in *Visa Requirements*", which survives a rename and
    a re-chunking.
    """

    title: str
    content: str
    #: Ordering hint for supersession chains. Higher supersedes lower.
    revision: int = 1
    #: Provenance status this document's passages are seeded with.
    #:
    #: This is the field that makes the supersession experiment real rather
    #: than rhetorical: a ``superseded`` document stays fully readable and
    #: fully indexed, and the only thing that hides it from a default query is
    #: the retrieval layer's status filter. If that filter is doing its job,
    #: current-value questions find the current text and history questions need
    #: an explicit opt-in.
    information_status: str = "current"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One question with a mechanically checkable expectation."""

    id: str
    category: CaseCategory
    question: str
    #: Document titles that contain the answer. Empty means "nothing does",
    #: which is the ground truth for an unanswerable case.
    relevant_titles: tuple[str, ...]
    #: Substrings that a correct answer must contain. Empty for abstention cases.
    must_contain: tuple[str, ...] = ()
    #: Substrings that indicate a wrong or fabricated answer.
    must_not_contain: tuple[str, ...] = ()
    #: True when the only correct behaviour is to abstain.
    expect_abstention: bool = False
    #: Why this expectation is correct. Required: an unexplained ground truth
    #: is an opinion, and opinions cannot be scored.
    basis: str = ""
    notes: str = ""
    #: Which half of the evaluation this case belongs to.
    #:
    #: Any decision that involves choosing a number — an evidence threshold, a
    #: cut-off, a floor — must be made on ``calibration`` cases only. Reporting
    #: that same number's performance on the cases it was fitted to would be
    #: circular, so ``evaluation`` cases are never inspected while calibrating.
    split: str = "evaluation"

    def __post_init__(self) -> None:
        if not self.basis:
            raise ValueError(f"case {self.id} has no recorded basis for its ground truth")
        if self.expect_abstention and self.must_contain:
            raise ValueError(f"case {self.id} expects abstention but requires content")
        if not self.expect_abstention and not self.must_contain:
            raise ValueError(f"case {self.id} expects an answer but names no required content")
        if self.split not in {"calibration", "evaluation"}:
            raise ValueError(f"case {self.id} has unknown split {self.split!r}")
        if self.expect_abstention and self.relevant_titles:
            raise ValueError(f"case {self.id} expects abstention but claims relevant documents")


@dataclass(frozen=True, slots=True)
class EvalDataset:
    """A versioned corpus plus its questions."""

    name: str
    version: str
    documents: tuple[EvalDocument, ...]
    cases: tuple[EvalCase, ...]
    description: str = ""
    #: Set when the corpus is derived from real material, to record its licence.
    licence: str = "Synthetic, authored for MNEMOS evaluation"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate case ids in dataset")
        allowed = {"current", "superseded", "archived"}
        for doc in self.documents:
            if doc.information_status not in allowed:
                raise ValueError(
                    f"document {doc.title!r} has unknown information_status "
                    f"{doc.information_status!r}; expected one of {sorted(allowed)}"
                )
        titles = [doc.title for doc in self.documents]
        if len(titles) != len(set(titles)):
            raise ValueError("duplicate document titles in dataset")
        known = set(titles)
        for case in self.cases:
            missing = set(case.relevant_titles) - known
            if missing:
                raise ValueError(f"case {case.id} refers to unknown documents: {sorted(missing)}")

    @property
    def fingerprint(self) -> str:
        """Stable digest of content, so a result can be tied to its dataset."""
        payload = {
            "name": self.name,
            "version": self.version,
            "documents": [
                {
                    "title": d.title,
                    "hash": d.content_hash,
                    "revision": d.revision,
                    "status": d.information_status,
                }
                for d in sorted(self.documents, key=lambda d: d.title)
            ],
            "cases": [
                {
                    "id": c.id,
                    "question": c.question,
                    "category": c.category.value,
                    "relevant": list(c.relevant_titles),
                }
                for c in sorted(self.cases, key=lambda c: c.id)
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def split(self, name: str) -> list[EvalCase]:
        """Cases belonging to one split, in a stable order."""
        return [case for case in self.cases if case.split == name]

    def by_category(self) -> dict[CaseCategory, list[EvalCase]]:
        grouped: dict[CaseCategory, list[EvalCase]] = {}
        for case in self.cases:
            grouped.setdefault(case.category, []).append(case)
        return grouped

    def titles(self) -> list[str]:
        return [doc.title for doc in self.documents]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "licence": self.licence,
            "fingerprint": self.fingerprint,
            "documents": [
                {
                    "title": d.title,
                    "revision": d.revision,
                    "status": d.information_status,
                    "content": d.content,
                }
                for d in self.documents
            ],
            "cases": [
                {
                    "id": c.id,
                    "category": c.category.value,
                    "question": c.question,
                    "relevant_titles": list(c.relevant_titles),
                    "must_contain": list(c.must_contain),
                    "must_not_contain": list(c.must_not_contain),
                    "expect_abstention": c.expect_abstention,
                    "basis": c.basis,
                    "notes": c.notes,
                }
                for c in self.cases
            ],
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, sort_keys=True), encoding="utf-8")
        return path


__all__ = [
    "CaseCategory",
    "EvalCase",
    "EvalDataset",
    "EvalDocument",
]
