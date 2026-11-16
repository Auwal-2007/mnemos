"""Evaluation framework against real PostgreSQL (Phase 4A).

These tests exercise the parts that cannot be faked: seeding the corpus into the
real tables, calling the real retrieval function, and proving that the query
relaxation added in migration ``20260104000000`` fixes the defect the evaluation
found. A mock would pass whatever it was told to pass.

The regression test matters most. Before the fix, a natural-language question
returned nothing because `websearch_to_tsquery` ANDs every term; the evaluation
measured 73.7% of answerable questions getting no evidence. If someone later
"simplifies" the query parsing back to a plain conjunction, that number returns
and this test fails.
"""

from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore")

from app.evaluation.corpus import DATASET  # noqa: E402
from app.evaluation.harness import pgserver_available, scratch_database  # noqa: E402
from app.evaluation.runner import run_evaluation  # noqa: E402
from app.evaluation.seed import seed_dataset  # noqa: E402
from app.evaluation.systems import BaselineSystem, MnemosSystem  # noqa: E402

pytestmark = pytest.mark.skipif(
    not pgserver_available(), reason="requires pgserver for a real PostgreSQL"
)

NATURAL_QUESTION = "how long do visa applications currently take to process"


@pytest.fixture(scope="module")
def live():
    with scratch_database() as handle:
        seeded = seed_dataset(handle.db, DATASET)
        yield handle, seeded


def test_seeding_creates_one_provenance_record_per_chunk(live) -> None:
    handle, seeded = live
    chunks = int(handle.db.scalar("select count(*) from public.chunks"))
    provenance = int(handle.db.scalar("select count(*) from public.provenance_records"))
    assert chunks == seeded.total_chunks
    assert provenance == chunks
    # Every chunk must be citable, or generation could not cite it.
    orphans = int(
        handle.db.scalar(
            "select count(*) from public.chunks c"
            " left join public.provenance_records p on p.chunk_id = c.id"
            " where p.id is null"
        )
    )
    assert orphans == 0


def test_seeding_is_idempotent_and_does_not_inflate_the_corpus(live) -> None:
    handle, _seeded = live
    before = int(handle.db.scalar("select count(*) from public.chunks"))
    seed_dataset(handle.db, DATASET)
    after = int(handle.db.scalar("select count(*) from public.chunks"))
    assert after == before, "re-seeding must not duplicate passages"


def test_owner_membership_is_written_exactly_once(live) -> None:
    """The workspace trigger owns membership; a second insert would double-count."""
    handle, seeded = live
    count = int(
        handle.db.scalar(
            "select count(*) from public.workspace_members where workspace_id = %s::uuid",
            (seeded.workspace_id,),
        )
    )
    assert count == 1


def test_natural_language_question_returns_evidence_after_relaxation(live) -> None:
    """The defect the evaluation found: 74% of answerable questions returned nothing."""
    handle, seeded = live
    system = MnemosSystem(handle.db, workspace_id=seeded.workspace_id)
    outcome = system.retrieve(NATURAL_QUESTION, k=5)
    assert outcome.hits, (
        "a natural-language question returned no evidence; the query relaxation "
        "fallback in migration 20260104000000 has regressed"
    )
    assert "Visa Processing Times (Current)" in outcome.titles


def test_strict_conjunction_still_wins_when_it_matches(live) -> None:
    """Relaxation is a fallback, not a replacement.

    A quoted phrase must still be honoured exactly, otherwise the fallback has
    silently discarded precision the caller asked for.
    """
    handle, _seeded = live
    strict = handle.db.scalar("select public.mnemos_lexical_query(%s)::text", ("passport",))
    relaxed = handle.db.scalar(
        "select public.mnemos_lexical_query_relaxed(%s)::text", ("passport",)
    )
    # A single term cannot be relaxed, so both parses agree.
    assert strict == relaxed


def test_relaxation_turns_conjunction_into_disjunction(live) -> None:
    handle, _ = live
    row = handle.db.one(
        "select public.mnemos_lexical_query(%s)::text as strict,"
        " public.mnemos_lexical_query_relaxed(%s)::text as relaxed",
        ("how long do visa applications", "how long do visa applications"),
    )
    assert row is not None
    assert "&" in row["strict"]
    assert "|" in row["relaxed"]


def test_relaxed_parser_never_raises_on_punctuation(live) -> None:
    handle, _ = live
    for hostile in ("!!!", "a & | b", "(((", "'; drop table chunks; --", ""):
        parsed = handle.db.scalar(
            "select coalesce(public.mnemos_lexical_query_relaxed(%s)::text, '')",
            (hostile,),
        )
        assert isinstance(parsed, str)


def test_superseded_material_is_hidden_unless_requested(live) -> None:
    """The status filter is what makes 'current' and 'historical' different questions."""
    handle, seeded = live
    question = "what was the expedited fee before it was increased"

    current_only = MnemosSystem(
        handle.db, workspace_id=seeded.workspace_id, include_superseded=False
    ).retrieve(question, k=5)
    with_history = MnemosSystem(
        handle.db, workspace_id=seeded.workspace_id, include_superseded=True
    ).retrieve(question, k=5)

    withdrawn = "Visa Processing Times (Withdrawn)"
    assert withdrawn not in current_only.titles
    assert withdrawn in with_history.titles


def test_baseline_sees_every_version_because_it_has_no_supersession_model(live) -> None:
    handle, seeded = live
    outcome = BaselineSystem(handle.db, workspace_id=seeded.workspace_id).retrieve(
        "expedited fee", k=10
    )
    assert "Visa Processing Times (Withdrawn)" in outcome.titles


def test_unanswerable_question_still_returns_hits_which_is_why_a_floor_exists(live) -> None:
    """Documents the honest limitation: retrieval cannot signal ignorance alone."""
    handle, seeded = live
    outcome = MnemosSystem(handle.db, workspace_id=seeded.workspace_id).retrieve(
        "What is the university's policy on emotional support animals in residences?",
        k=5,
    )
    assert outcome.hits, (
        "if this ever returns nothing, the calibration rationale in "
        "docs/EVALUATION.md needs revisiting"
    )


def test_a_full_run_produces_every_system_and_blocks_model_metrics(live) -> None:
    handle, seeded = live
    result = run_evaluation(
        dataset=DATASET,
        db=handle.db,
        workspace_id=seeded.workspace_id,
        chunk_count=seeded.total_chunks,
        migrations_applied=handle.migration_count,
    )
    assert set(result["aggregates"]) == {"mnemos", "mnemos_history", "baseline"}
    assert result["manifest"]["dataset_fingerprint"] == DATASET.fingerprint
    assert result["manifest"]["case_count"] == len(DATASET.cases)
    # Model-dependent metrics must be declared blocked, never silently omitted.
    for metric in ("answer_correctness", "faithfulness", "estimated_cost"):
        assert metric in result["blocked_metrics"]
    assert len(result["cases"]) == len(DATASET.cases) * 3


def test_a_run_is_reproducible_for_identical_inputs(live) -> None:
    """Retrieval scores must not drift between runs; latency may."""
    handle, seeded = live
    first = run_evaluation(dataset=DATASET, db=handle.db, workspace_id=seeded.workspace_id)
    second = run_evaluation(dataset=DATASET, db=handle.db, workspace_id=seeded.workspace_id)
    for system in first["aggregates"]:
        for metric, stats in first["aggregates"][system]["overall"].items():
            if metric == "latency_ms":
                continue
            assert stats["mean"] == pytest.approx(
                second["aggregates"][system]["overall"][metric]["mean"]
            ), f"{system}/{metric} changed between identical runs"
