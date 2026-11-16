"""Calibrate the evidence-sufficiency floor (Phase 4A).

The problem
-----------
Relaxing the lexical query (see migration ``20260104000000``) bought recall and
cost abstention. With terms OR-ed together, almost any question matches
*something*, so "did retrieval return a passage?" stopped being a useful test of
"is there evidence?". The measured consequence was unambiguous: abstention
accuracy fell to 0.000 across every system in the corpus.

A system that cannot recognise its own ignorance is worse than one that
occasionally returns nothing, because the generation stage is then free to
produce an answer with a citation attached to unrelated text.

The rule this module follows
----------------------------
Choose the threshold on ``split="calibration"`` cases only, then report it on
``split="evaluation"`` cases, and never the other way round. Fitting a number on
the cases you then quote it against is circular, and the resulting figure looks
better than the system is. The two splits are disjoint by construction and the
chosen value is only ever scored on the held-out half.

What is being thresholded
-------------------------
``ts_rank_cd`` of the best matching passage — the retriever's own strength
signal. The fused RRF score is deliberately *not* used: RRF discards magnitude
by design (that is what makes it robust across retrievers), so it cannot
distinguish a strong topical match from a stray common word.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.dataset import EvalCase
from app.evaluation.systems import RetrievalSystem

#: Floors swept, in ``ts_rank_cd`` units. The grid is fixed in advance rather
#: than searched finely, so the chosen value is one of a small, stateable set.
FLOOR_GRID: tuple[float, ...] = (
    0.0,
    0.01,
    0.02,
    0.03,
    0.05,
    0.075,
    0.1,
    0.15,
    0.2,
    0.25,
    0.3,
    0.35,
    0.4,
    0.5,
    0.6,
    0.8,
)

#: The floor chosen on the calibration split. Recorded here so the product, the
#: report and the tests all refer to one number.
#:
#: Chosen 2026-11-16 from the calibration split of dataset
#: ``mnemos-university-policy`` v1.0.0. The grid is flat between 0.25 and 0.50,
#: and the documented tie-break picks the lowest equivalent value: of two equally
#: accurate thresholds, the one that abstains less often is preferred, because a
#: spurious refusal is visible to the user while an over-eager answer can at
#: least be inspected against its citations.
#:
#: This value is **not** a property of the system. It is the best available
#: cut-off on one signal that the calibration showed to be inadequate: see
#: ``docs/EVALUATION.md`` for the case where an answerable question scores below
#: an unanswerable one. It must be re-derived once semantic retrieval is
#: available.
CALIBRATED_FLOOR = 0.25


@dataclass(slots=True)
class FloorScore:
    """Outcome of one candidate floor on one split."""

    floor: float
    abstention_accuracy: float
    false_abstention: float
    missed_abstention: float
    answered_correctly: int
    answered_total: int
    abstenained_correctly: int
    abstain_total: int

    def to_json(self) -> dict[str, Any]:
        return {
            "floor": self.floor,
            "abstention_accuracy": self.abstention_accuracy,
            "false_abstention": self.false_abstention,
            "missed_abstention": self.missed_abstention,
            "answered": f"{self.answered_correctly}/{self.answered_total}",
            "abstained": f"{self.abstenained_correctly}/{self.abstain_total}",
        }


def score_floor(
    floor: float,
    cases: list[EvalCase],
    outcomes: dict[str, Any],
    *,
    system: str,
) -> FloorScore:
    """Evaluate one candidate floor over a set of cases.

    A false abstention (refusing when evidence exists) and a missed abstention
    (answering when it does not) are counted separately. They do not have equal
    cost — a false abstention is unhelpful, a missed abstention is a fabrication
    pathway — so a single accuracy number is reported alongside both.
    """
    answered_total = 0
    answered_correctly = 0
    abstain_total = 0
    abstained_correctly = 0
    correct_overall = 0

    for case in cases:
        outcome = outcomes[case.id]
        # outcomes maps case_id -> RetrievalOutcome for this system
        passed = outcome.sufficient(floor)
        if case.expect_abstention:
            abstain_total += 1
            if not passed:
                abstained_correctly += 1
                correct_overall += 1
        else:
            answered_total += 1
            if passed:
                answered_correctly += 1
                correct_overall += 1

    total = len(cases)
    return FloorScore(
        floor=floor,
        abstention_accuracy=correct_overall / total if total else 0.0,
        false_abstention=(1.0 - (answered_correctly / answered_total) if answered_total else 0.0),
        missed_abstention=(1.0 - (abstained_correctly / abstain_total) if abstain_total else 0.0),
        answered_correctly=answered_correctly,
        answered_total=answered_total,
        abstenained_correctly=abstained_correctly,
        abstain_total=abstain_total,
    )


def _collect(system: RetrievalSystem, cases: list[EvalCase], *, k: int) -> dict[str, Any]:
    return {case.id: system.retrieve(case.question, k=k) for case in cases}


def select_floor(
    *,
    system: RetrievalSystem,
    calibration_cases: list[EvalCase],
    k: int = 5,
) -> tuple[float, list[FloorScore]]:
    """Choose the floor that maximises abstention accuracy on calibration cases.

    Ties are broken toward the *lower* floor. When two thresholds perform
    equally, the more conservative choice is to answer more and abstain less,
    because a wrongly-triggered abstention is visible to the user while an
    over-eager answer is at least inspectable against its citations.
    """
    outcomes = _collect(system, calibration_cases, k=k)
    scored = [
        score_floor(floor, calibration_cases, outcomes, system=system.name) for floor in FLOOR_GRID
    ]
    best = max(scored, key=lambda item: (item.abstention_accuracy, -item.floor))
    return best.floor, scored


def evaluate_floor(
    *,
    system: RetrievalSystem,
    cases: list[EvalCase],
    floor: float,
    k: int = 5,
) -> FloorScore:
    """Score a fixed floor on a set of cases (the held-out split)."""
    outcomes = _collect(system, cases, k=k)
    return score_floor(floor, cases, outcomes, system=system.name)


__all__ = [
    "FLOOR_GRID",
    "FloorScore",
    "evaluate_floor",
    "score_floor",
    "select_floor",
]
