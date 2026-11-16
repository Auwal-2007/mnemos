"""Evaluation runner (Phase 4A).

A run is a single recorded artefact: the dataset fingerprint, the retrieval
configuration, every per-case outcome, and the aggregate metrics. Re-running the
same dataset and configuration must reproduce it, so nothing here depends on
wall-clock time, dict ordering, or an unrecorded default.

Two configurations of MNEMOS are measured, because they answer different
questions:

``mnemos``
    Superseded passages excluded — the product default. This is what a user
    asking "what is the current fee?" should get.

``mnemos_history``
    Same system with superseded passages included. A user asking "what *was*
    the fee?" needs this. Measuring both shows whether history is reachable at
    all, which a single configuration would hide.

The baseline has no such switch because a conventional pipeline has no concept
of supersession — it sees every version, always. That asymmetry is the point,
and it is reported rather than equalised away.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.evaluation.dataset import EvalCase, EvalDataset
from app.evaluation.metrics import (
    MetricAccumulator,
    citation_precision,
    citation_recall,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.systems import (
    BaselineSystem,
    MnemosSystem,
    RetrievalOutcome,
    RetrievalSystem,
)

#: K values scored. Documented in the report alongside every number.
DEFAULT_K_VALUES: tuple[int, ...] = (1, 3, 5)


@dataclass(slots=True)
class CaseOutcome:
    """One system's answer to one case, with the metrics derived from it."""

    case_id: str
    category: str
    question: str
    system: str
    expected_titles: list[str]
    expect_abstention: bool
    retrieved_titles: list[str]
    retrieved_chunk_ids: list[str]
    answered: bool
    latency_ms: float
    mode: str
    metrics: dict[str, float | None] = field(default_factory=dict)
    #: Set when the answer-level check could not be performed at all, so an
    #: unavailable metric is distinguishable from a failing one.
    blocked: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def score_case(
    case: EvalCase, outcome: RetrievalOutcome, *, k_values: tuple[int, ...]
) -> dict[str, Any]:
    """Compute every retrieval-level metric for one case.

    Answer-level metrics (correctness, faithfulness, unsupported-answer rate) are
    deliberately absent: they require a generation model, and inventing them
    from retrieval output would be the exact fabrication this project forbids.
    They are reported as blocked instead.
    """
    relevant = set(case.relevant_titles)
    titles = outcome.titles
    observed: dict[str, float | None] = {}

    for k in k_values:
        observed[f"recall@{k}"] = recall_at_k(titles, relevant, k)
        observed[f"precision@{k}"] = precision_at_k(titles, relevant, k)
        observed[f"ndcg@{k}"] = ndcg_at_k(titles, relevant, k)
    observed["mrr"] = reciprocal_rank(titles, relevant)

    # Abstention is judged at the retrieval level: did the system return usable
    # evidence exactly when evidence exists?
    if case.expect_abstention:
        observed["abstention_correct"] = 0.0 if outcome.answered else 1.0
    else:
        observed["false_abstention"] = 0.0 if outcome.answered else 1.0
        observed["missed_abstention"] = 0.0

    # Citation metrics use the documents actually retrieved as the citation set,
    # because at this layer the retrieved passages *are* the citations the
    # answer would be built from.
    observed["citation_precision"] = citation_precision(titles, relevant)
    observed["citation_recall"] = citation_recall(titles, relevant)

    observed["latency_ms"] = outcome.latency_ms
    return observed


def _aggregate(outcomes: list[CaseOutcome], *, k_values: tuple[int, ...]) -> dict[str, Any]:
    """Aggregate over all cases and per category.

    Per-category totals matter more than the overall figure: an aggregate can
    look respectable while one category is uniformly failing.
    """
    overall = MetricAccumulator()
    by_category: dict[str, MetricAccumulator] = {}
    for outcome in outcomes:
        bucket = by_category.setdefault(outcome.category, MetricAccumulator())
        for name, value in outcome.metrics.items():
            overall.add(name, value)
            bucket.add(name, value)

    def render(acc: MetricAccumulator) -> dict[str, Any]:
        return acc.as_dict()

    return {
        "overall": render(overall),
        "by_category": {name: render(acc) for name, acc in sorted(by_category.items())},
        "case_count": len(outcomes),
        "latency": {
            "mean_ms": _mean([o.latency_ms for o in outcomes]),
            "p50_ms": _percentile([o.latency_ms for o in outcomes], 50),
            "p95_ms": _percentile([o.latency_ms for o in outcomes], 95),
        },
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (pct / 100.0)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


@dataclass(slots=True)
class RunManifest:
    """Everything needed to reproduce a run, recorded with its results."""

    run_id: str
    started_at: str
    finished_at: str = ""
    dataset_name: str = ""
    dataset_version: str = ""
    dataset_fingerprint: str = ""
    case_count: int = 0
    document_count: int = 0
    chunk_count: int = 0
    k_values: tuple[int, ...] = DEFAULT_K_VALUES
    candidate_count: int = 30
    systems: tuple[str, ...] = ()
    embedding_provider: str = "none (no provider configured; lexical only)"
    generation_provider: str = "none (answer-level metrics blocked)"
    postgres_version: str = ""
    migrations_applied: int = 0
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["k_values"] = list(self.k_values)
        payload["systems"] = list(self.systems)
        return payload


def run_evaluation(
    *,
    dataset: EvalDataset,
    db: Any,
    workspace_id: str,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    candidate_count: int = 30,
    postgres_version: str = "",
    migrations_applied: int = 0,
    chunk_count: int = 0,
) -> dict[str, Any]:
    """Execute every case against every system and return a complete result.

    The return value is JSON-serialisable on purpose: it is written to disk
    verbatim as the record of the run.
    """
    started = datetime.now(UTC)
    k_max = max(k_values)

    systems: list[tuple[str, RetrievalSystem]] = [
        (
            "mnemos",
            MnemosSystem(
                db,
                workspace_id=workspace_id,
                candidate_count=candidate_count,
                include_superseded=False,
            ),
        ),
        (
            "mnemos_history",
            MnemosSystem(
                db,
                workspace_id=workspace_id,
                candidate_count=candidate_count,
                include_superseded=True,
            ),
        ),
        ("baseline", BaselineSystem(db, workspace_id=workspace_id)),
    ]

    per_system: dict[str, list[CaseOutcome]] = {}
    raw: list[dict[str, Any]] = []

    for name, system in systems:
        outcomes: list[CaseOutcome] = []
        for case in dataset.cases:
            retrieval = system.retrieve(case.question, k=k_max)
            metrics = score_case(case, retrieval, k_values=k_values)
            outcome = CaseOutcome(
                case_id=case.id,
                category=case.category.value,
                question=case.question,
                system=name,
                expected_titles=list(case.relevant_titles),
                expect_abstention=case.expect_abstention,
                retrieved_titles=retrieval.titles,
                retrieved_chunk_ids=[hit.chunk_id for hit in retrieval.hits],
                answered=retrieval.answered,
                latency_ms=retrieval.latency_ms,
                mode=retrieval.mode,
                metrics=metrics,
                blocked=[
                    "answer_correctness",
                    "faithfulness",
                    "unsupported_answer_rate",
                    "token_usage",
                    "estimated_cost",
                ],
            )
            outcomes.append(outcome)
            raw.append(outcome.to_json())
        per_system[name] = outcomes

    aggregates = {
        name: _aggregate(outcomes, k_values=k_values) for name, outcomes in per_system.items()
    }

    finished = datetime.now(UTC)
    manifest = RunManifest(
        run_id=f"{dataset.version}-{started.strftime('%Y%m%dT%H%M%SZ')}",
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        dataset_fingerprint=dataset.fingerprint,
        case_count=len(dataset.cases),
        document_count=len(dataset.documents),
        chunk_count=chunk_count,
        k_values=k_values,
        candidate_count=candidate_count,
        systems=tuple(name for name, _ in systems),
        postgres_version=postgres_version,
        migrations_applied=migrations_applied,
    )

    return {
        "manifest": manifest.to_json(),
        "aggregates": aggregates,
        "cases": raw,
        "blocked_metrics": {
            "answer_correctness": (
                "requires a generation model; no provider is reachable from the "
                "environment that produced this run"
            ),
            "faithfulness": "requires a generation model",
            "unsupported_answer_rate": "requires a generation model",
            "claim_attribution": "requires a generation model plus verification",
            "token_usage": "requires a provider response",
            "estimated_cost": "requires provider billing data; never estimated from assumption",
        },
    }


def summarise(result: dict[str, Any]) -> str:
    """One-screen summary for the console."""
    lines: list[str] = []
    manifest = result["manifest"]
    lines.append(f"run      {manifest['run_id']}")
    lines.append(
        f"dataset  {manifest['dataset_name']} v{manifest['dataset_version']} "
        f"({manifest['case_count']} cases, {manifest['document_count']} docs, "
        f"{manifest['chunk_count']} chunks)"
    )
    lines.append(f"embed    {manifest['embedding_provider']}")
    lines.append("")
    header = f"{'metric':22}" + "".join(f"{name:>16}" for name in result["aggregates"])
    lines.append(header)
    lines.append("-" * len(header))
    for metric in (
        "recall@1",
        "recall@3",
        "recall@5",
        "precision@5",
        "mrr",
        "ndcg@5",
        "citation_precision",
        "citation_recall",
        "abstention_correct",
        "false_abstention",
    ):
        row = f"{metric:22}"
        for name in result["aggregates"]:
            stats = result["aggregates"][name]["overall"].get(metric)
            value = stats["mean"] if stats else None
            row += f"{'—' if value is None else f'{value:.3f}':>16}"
        lines.append(row)
    return "\n".join(lines)


__all__ = [
    "DEFAULT_K_VALUES",
    "CaseOutcome",
    "RunManifest",
    "run_evaluation",
    "score_case",
    "summarise",
]
