"""Evaluation framework (Phase 4A).

Reusable pieces:

* :mod:`app.evaluation.dataset` — dataset and case schema with versioning.
* :mod:`app.evaluation.corpus` — the seeded corpus and its questions.
* :mod:`app.evaluation.metrics` — precisely defined metrics.
* :mod:`app.evaluation.systems` — MNEMOS and the conventional RAG baseline.
* :mod:`app.evaluation.harness` — real PostgreSQL + real migration substrate.
* :mod:`app.evaluation.runner` — executes a run and records it.
* :mod:`app.evaluation.report` — renders a Markdown report from a run.

Run with ``python -m app.evaluation.run``.
"""

from app.evaluation.corpus import DATASET
from app.evaluation.dataset import CaseCategory, EvalCase, EvalDataset, EvalDocument

__all__ = [
    "DATASET",
    "CaseCategory",
    "EvalCase",
    "EvalDataset",
    "EvalDocument",
]
