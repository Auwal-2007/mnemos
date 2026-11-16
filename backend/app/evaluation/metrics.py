"""Evaluation metrics (Phase 4A).

Every metric here is defined before it is computed, because a metric whose
definition is decided after seeing the numbers is not a measurement.

Precise definitions
-------------------
Recall@K
    For one case: the fraction of ground-truth relevant documents that appear in
    the top K retrieved passages, counting a document as retrieved if *any* of
    its passages is in the top K. For an unanswerable case there is no relevant
    set, so recall is undefined and the case is excluded from the recall mean
    (it is scored by abstention instead, not by a zero that would drag the mean
    down for a defensible reason).

Precision@K
    The fraction of the top K retrieved passages whose document is relevant.
    Unlike recall, this *is* defined for unanswerable cases: the correct value is
    0, because every passage returned is, by construction, irrelevant. Including
    them is deliberate — a system that floods the context on an unanswerable
    question is doing something wrong even if it abstains afterwards.

MRR (Mean Reciprocal Rank)
    The reciprocal of the rank of the first relevant passage; 0 if none appears.
    Undefined for unanswerable cases, excluded from the mean for the reason
    given above.

nDCG@K
    Graded relevance with a binary gain (1 for a relevant document, 0
    otherwise), discounted logarithmically by position. With binary gains and a
    single relevant document this reduces to 1/log2(rank+1), but it is computed
    generally so that multi-document cases are handled correctly. Cases with no
    relevant documents are excluded.

Abstention accuracy
    Over *all* cases: 1 if the system abstained exactly when it should have, else
    0. Reported as a rate. This is the metric that punishes both failure modes:
    answering when the corpus is silent, and abstaining when it is not.

False abstention rate
    Among cases that *should* have been answered, the fraction the system
    abstained on. Distinct from abstention accuracy because the two failures have
    different user consequences: a false abstention is a system that refuses to
    help; a missed abstention is a system that fabricates.

Unsupported answer rate
    Among cases that were answered, the fraction whose answer did not contain the
    required ground-truth content. This is the closest automatic proxy for
    fabrication, and it is labelled a proxy because a substring check cannot
    distinguish a subtly wrong answer from a right one phrased differently. That
    limitation is stated in the report rather than hidden.

Citation precision / recall
    Precision: of the citations the system emitted, the fraction pointing at a
    document that is relevant. Recall: of the relevant documents, the fraction
    actually cited. Both are computed over answered cases only; an answer with no
    citations scores 0 on recall and is counted, not skipped.

Why no single headline number
    A weighted composite would let a strong factual score hide a broken
    abstention. The runner reports per-category results and the report shows the
    table; there is deliberately no aggregate "MNEMOS score".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def recall_at_k(retrieved_titles: list[str], relevant: set[str], k: int) -> float | None:
    """Fraction of relevant documents present in the top ``k``. None if undefined."""
    if not relevant:
        return None
    top = retrieved_titles[:k]
    found = relevant & set(top)
    return len(found) / len(relevant)


def precision_at_k(retrieved_titles: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the top ``k`` that is relevant. Defined for empty relevant sets."""
    top = retrieved_titles[:k]
    if not top:
        return 0.0
    if not relevant:
        # Every returned passage is irrelevant by construction.
        return 0.0
    return sum(1 for title in top if title in relevant) / len(top)


def reciprocal_rank(retrieved_titles: list[str], relevant: set[str]) -> float | None:
    """1/rank of the first relevant passage; 0.0 if none; None if undefined."""
    if not relevant:
        return None
    for index, title in enumerate(retrieved_titles, start=1):
        if title in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved_titles: list[str], relevant: set[str], k: int) -> float | None:
    """Normalised discounted cumulative gain with binary gains."""
    if not relevant:
        return None
    dcg = 0.0
    for index, title in enumerate(retrieved_titles[:k], start=1):
        if title in relevant:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    if idcg == 0:
        return None
    return dcg / idcg


def citation_precision(cited_titles: list[str], relevant: set[str]) -> float | None:
    """Fraction of emitted citations that point at a relevant document."""
    if not cited_titles:
        return None
    if not relevant:
        return 0.0
    return sum(1 for title in cited_titles if title in relevant) / len(cited_titles)


def citation_recall(cited_titles: list[str], relevant: set[str]) -> float | None:
    """Fraction of relevant documents that were actually cited."""
    if not relevant:
        return None
    if not cited_titles:
        return 0.0
    return len(relevant & set(cited_titles)) / len(relevant)


def contains_all(text: str, required: tuple[str, ...]) -> bool:
    """True when every required substring appears, case-insensitively."""
    lowered = text.lower()
    return all(term.lower() in lowered for term in required)


def contains_any(text: str, forbidden: tuple[str, ...]) -> bool:
    """True when any forbidden substring appears, case-insensitively."""
    lowered = text.lower()
    return any(term.lower() in lowered for term in forbidden)


def mean(values: list[float]) -> float | None:
    """Arithmetic mean, or None when there is nothing to average.

    Returning None rather than 0.0 matters: a metric with no applicable cases is
    unmeasured, not zero, and reporting 0.0 would read as total failure.
    """
    if not values:
        return None
    return sum(values) / len(values)


@dataclass(slots=True)
class MetricAccumulator:
    """Collects per-case values and reports means that skip undefined entries."""

    values: dict[str, list[float]] = field(default_factory=dict)

    def add(self, name: str, value: float | None) -> None:
        if value is None:
            return
        self.values.setdefault(name, []).append(value)

    def mean(self, name: str) -> float | None:
        return mean(self.values.get(name, []))

    def count(self, name: str) -> int:
        return len(self.values.get(name, []))

    def as_dict(self) -> dict[str, Any]:
        return {
            name: {"mean": mean(vals), "n": len(vals)} for name, vals in sorted(self.values.items())
        }


__all__ = [
    "MetricAccumulator",
    "citation_precision",
    "citation_recall",
    "contains_all",
    "contains_any",
    "mean",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
