"""Command-line entry point for an evaluation run (Phase 4A).

Usage::

    python -m app.evaluation.run                     # write to backend/eval-results
    python -m app.evaluation.run --label before-fix  # tag the run directory
    python -m app.evaluation.run --no-report         # results only

Artefacts written per run, all deterministic given the same inputs:

    <out>/<label>/results.json     per-case outcomes, aggregates, manifest
    <out>/<label>/dataset.json     the exact corpus and questions used
    <out>/<label>/report.md        human-readable report

The dataset is written next to the results so a result can never drift from the
data that produced it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.evaluation.corpus import DATASET
from app.evaluation.harness import pgserver_available, scratch_database
from app.evaluation.report import render_report
from app.evaluation.runner import DEFAULT_K_VALUES, run_evaluation, summarise
from app.evaluation.seed import seed_dataset

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "eval-results"


def _parse_k(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(part) for part in raw.split(",") if part.strip()}))
    if not values or min(values) < 1:
        raise argparse.ArgumentTypeError("k values must be positive integers")
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.evaluation.run",
        description="Run the MNEMOS retrieval evaluation against a real PostgreSQL.",
    )
    parser.add_argument("--label", default="latest", help="name of the output subdirectory")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="output root")
    parser.add_argument(
        "--k", type=_parse_k, default=DEFAULT_K_VALUES, help="comma-separated K values"
    )
    parser.add_argument("--candidates", type=int, default=30, help="fusion candidate pool size")
    parser.add_argument("--no-report", action="store_true", help="skip Markdown report")
    parser.add_argument("--json", action="store_true", help="print results JSON to stdout")
    args = parser.parse_args(argv)

    if not pgserver_available():
        print(
            "error: pgserver is not available, so the evaluation cannot run.\n"
            "       The evaluation deliberately requires real PostgreSQL: a mocked\n"
            "       search would measure the mock. Install pgserver and retry.",
            file=sys.stderr,
        )
        return 2

    with scratch_database() as handle:
        seeded = seed_dataset(handle.db, DATASET)
        postgres_version = handle.db.scalar("select version()")
        result = run_evaluation(
            dataset=DATASET,
            db=handle.db,
            workspace_id=seeded.workspace_id,
            k_values=args.k,
            candidate_count=args.candidates,
            postgres_version=postgres_version,
            migrations_applied=handle.migration_count,
            chunk_count=seeded.total_chunks,
        )

    out_dir = args.out / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    DATASET.write(out_dir / "dataset.json")
    if not args.no_report:
        (out_dir / "report.md").write_text(render_report(result), encoding="utf-8")

    print(summarise(result))
    print()
    print(f"artefacts: {out_dir}")
    if args.json:
        print(json.dumps(result["aggregates"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
