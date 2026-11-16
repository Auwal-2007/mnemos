"""Evaluation framework tests (Phase 4A).

What these tests protect
------------------------
The evaluation is the instrument the project uses to judge itself, so its own
correctness matters more than most code. A metric with an off-by-one in the rank
arithmetic would quietly flatter every future result.

The tests are split by what they need:

* pure logic (metrics, dataset validation, calibration arithmetic) runs anywhere;
* database-dependent checks (seeding, real retrieval, threshold selection) run
  against a real PostgreSQL and skip when pgserver is unavailable.

Nothing here asserts a particular retrieval score. Scores change when the
retriever changes; these tests assert that the *measurement* is correct.
"""

from __future__ import annotations

import math

import pytest

from app.evaluation.calibrate import FLOOR_GRID, score_floor
from app.evaluation.corpus import DATASET
from app.evaluation.dataset import (
    CaseCategory,
    EvalCase,
    EvalDataset,
    EvalDocument,
)
from app.evaluation.metrics import (
    citation_precision,
    citation_recall,
    contains_all,
    contains_any,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.systems import Hit, RetrievalOutcome

# --- metric arithmetic ----------------------------------------------------


def test_recall_at_k_counts_a_document_once_however_many_passages_it_contributes() -> None:
    # "Library" contributes three passages; it is still one relevant document
    # found, so recall is 1.0, not 3.0.
    titles = ["Library", "Library", "Library", "Other"]
    assert recall_at_k(titles, {"Library"}, 3) == 1.0


def test_recall_at_k_is_undefined_without_relevant_documents() -> None:
    # Undefined rather than 0.0: an unanswerable case has no recall to fail.
    assert recall_at_k(["A"], set(), 5) is None


def test_recall_at_k_respects_the_cutoff() -> None:
    assert recall_at_k(["A", "B"], {"B"}, 1) == 0.0
    assert recall_at_k(["A", "B"], {"B"}, 2) == 1.0


def test_precision_at_k_is_defined_and_zero_when_nothing_is_relevant() -> None:
    # Deliberately 0 rather than undefined: returning passages for an
    # unanswerable question is a real behaviour that should be penalised.
    assert precision_at_k(["A", "B"], set(), 2) == 0.0
    assert precision_at_k(["A", "B"], {"A"}, 2) == 0.5


def test_precision_at_k_returns_zero_when_nothing_was_retrieved() -> None:
    assert precision_at_k([], {"A"}, 5) == 0.0


def test_reciprocal_rank_uses_one_based_positions() -> None:
    assert reciprocal_rank(["A", "B"], {"A"}) == 1.0
    assert reciprocal_rank(["A", "B"], {"B"}) == 0.5
    assert reciprocal_rank(["A", "B"], {"C"}) == 0.0
    assert reciprocal_rank(["A"], set()) is None


def test_ndcg_is_one_for_a_perfect_ordering_and_lower_for_a_delayed_hit() -> None:
    assert ndcg_at_k(["A"], {"A"}, 5) == pytest.approx(1.0)
    delayed = ndcg_at_k(["X", "A"], {"A"}, 5)
    assert delayed is not None
    assert delayed == pytest.approx(1 / math.log2(3))


def test_ndcg_handles_multiple_relevant_documents() -> None:
    perfect = ndcg_at_k(["A", "B"], {"A", "B"}, 5)
    assert perfect == pytest.approx(1.0)


def test_citation_precision_and_recall_are_separate_signals() -> None:
    # Two citations, one relevant: precision 0.5, recall 1.0.
    assert citation_precision(["A", "X"], {"A"}) == 0.5
    assert citation_recall(["A", "X"], {"A"}) == 1.0
    # No citations at all is a recall failure, not an undefined value.
    assert citation_recall([], {"A"}) == 0.0


def test_contains_helpers_are_case_insensitive() -> None:
    assert contains_all("Twenty Five working days", ("twenty five",))
    assert not contains_all("fifteen days", ("twenty five",))
    assert contains_any("fee is 85 USD", ("120", "85"))


def test_mean_returns_none_when_nothing_was_measured() -> None:
    # None forces the caller to print "—" rather than a misleading 0.000.
    assert mean([]) is None
    assert mean([1.0, 2.0]) == 1.5


# --- dataset validation ---------------------------------------------------


def _document(title: str = "Doc") -> EvalDocument:
    return EvalDocument(title=title, content="Some content about a topic.")


def _case(**overrides: object) -> EvalCase:
    base: dict[str, object] = {
        "id": "C-1",
        "category": CaseCategory.FACTUAL,
        "question": "A question?",
        "relevant_titles": ("Doc",),
        "must_contain": ("content",),
        "basis": "Doc states it.",
    }
    base.update(overrides)
    return EvalCase(**base)  # type: ignore[arg-type]


def test_case_without_a_basis_is_rejected() -> None:
    # An unexplained expectation is an opinion and cannot be scored.
    with pytest.raises(ValueError, match="no recorded basis"):
        _case(basis="")


def test_abstention_case_may_not_require_content_or_claim_relevance() -> None:
    with pytest.raises(ValueError, match="requires content"):
        _case(expect_abstention=True, must_contain=("x",))
    with pytest.raises(ValueError, match="claims relevant documents"):
        _case(expect_abstention=True, must_contain=(), relevant_titles=("Doc",))


def test_answerable_case_must_name_required_content() -> None:
    with pytest.raises(ValueError, match="names no required content"):
        _case(must_contain=())


def test_dataset_rejects_unknown_documents_and_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="unknown documents"):
        EvalDataset(
            name="d",
            version="1",
            documents=(_document("Doc"),),
            cases=(_case(relevant_titles=("Missing",)),),
        )
    with pytest.raises(ValueError, match="duplicate case ids"):
        EvalDataset(
            name="d",
            version="1",
            documents=(_document("Doc"),),
            cases=(_case(), _case()),
        )


def test_dataset_rejects_duplicate_document_titles_and_bad_status() -> None:
    with pytest.raises(ValueError, match="duplicate document titles"):
        EvalDataset(name="d", version="1", documents=(_document(), _document()), cases=())
    with pytest.raises(ValueError, match="unknown information_status"):
        EvalDataset(
            name="d",
            version="1",
            documents=(EvalDocument(title="X", content="y", information_status="stale"),),
            cases=(),
        )


def test_fingerprint_covers_status_so_a_result_cannot_be_matched_to_stale_data() -> None:
    base = EvalDataset(name="d", version="1", documents=(_document(),), cases=())
    changed = EvalDataset(
        name="d",
        version="1",
        documents=(EvalDocument(title="Doc", content="Some content about a topic.",
                                information_status="superseded"),),
        cases=(),
    )
    assert base.fingerprint != changed.fingerprint


# --- the shipped dataset --------------------------------------------------


def test_shipped_dataset_is_self_consistent_and_covers_every_category() -> None:
    assert len(DATASET.cases) >= 20
    covered = {case.category for case in DATASET.cases}
    assert covered == set(CaseCategory)


def test_every_required_answer_string_appears_in_the_corpus() -> None:
    """Ground truth must be derivable from the documents, not invented.

    This is the check that caught a case requiring the word "required" when the
    source said "mandatory": a correct answer would have failed it.
    """
    corpus = "\n".join(document.content for document in DATASET.documents).lower()
    ungrounded = [
        (case.id, term)
        for case in DATASET.cases
        if not case.expect_abstention
        for term in case.must_contain
        if term.lower() not in corpus
    ]
    assert ungrounded == []


def test_calibration_and_evaluation_splits_are_disjoint_and_both_populated() -> None:
    calibration = DATASET.split("calibration")
    evaluation = DATASET.split("evaluation")
    assert calibration and evaluation
    assert not ({c.id for c in calibration} & {c.id for c in evaluation})
    assert sum(1 for c in calibration if c.expect_abstention) >= 1


def test_each_document_carries_one_uniform_status() -> None:
    """A document must not mix current and withdrawn material.

    Marking a whole document superseded because one clause changed penalises any
    system that correctly filters stale text, so the corpus keeps each document
    internally consistent and splits the rest into separate documents.
    """
    statuses = {document.information_status for document in DATASET.documents}
    assert statuses <= {"current", "superseded", "archived"}
    assert "superseded" in statuses  # at least one genuinely withdrawn document


# --- calibration arithmetic ----------------------------------------------


def _outcome(strength: float) -> RetrievalOutcome:
    hit = Hit(
        chunk_id="c",
        document_title="Doc",
        content="text",
        score=0.01,
        rank=1,
        strength=strength,
    )
    return RetrievalOutcome(question="q", hits=(hit,), latency_ms=1.0, mode="lexical")


def test_floor_gating_distinguishes_answerable_from_unanswerable_cases() -> None:
    answerable = _case(id="A", relevant_titles=("Doc",))
    unanswerable = _case(
        id="U",
        relevant_titles=(),
        must_contain=(),
        expect_abstention=True,
    )
    outcomes = {"A": _outcome(0.9), "U": _outcome(0.0)}
    # A floor between the two separates them correctly.
    scored = score_floor(0.25, [answerable, unanswerable], outcomes, system="t")
    assert scored.abstention_accuracy == 1.0
    assert scored.false_abstention == 0.0
    assert scored.missed_abstention == 0.0


def test_floor_above_a_true_match_is_counted_as_false_abstention() -> None:
    answerable = _case(id="A", relevant_titles=("Doc",))
    scored = score_floor(0.9, [answerable], {"A": _outcome(0.1)}, system="t")
    assert scored.false_abstention == 1.0
    assert scored.abstention_accuracy == 0.0


def test_floor_below_a_spurious_match_is_counted_as_missed_abstention() -> None:
    unanswerable = _case(
        id="U", relevant_titles=(), must_contain=(), expect_abstention=True
    )
    scored = score_floor(0.0, [unanswerable], {"U": _outcome(0.01)}, system="t")
    assert scored.missed_abstention == 1.0
    assert scored.abstention_accuracy == 0.0


def test_floor_grid_is_ascending_and_starts_at_zero() -> None:
    assert FLOOR_GRID[0] == 0.0
    assert list(FLOOR_GRID) == sorted(FLOOR_GRID)


def test_empty_retrieval_is_never_sufficient() -> None:
    empty = RetrievalOutcome(question="q", hits=(), latency_ms=1.0, mode="lexical")
    assert empty.sufficient(0.0) is False
    assert empty.strongest == 0.0
