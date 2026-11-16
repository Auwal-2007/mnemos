"""The seeded evaluation corpus (Phase 4A).

Design constraints
------------------
1. **Every category must be reachable.** A corpus that only contains crisp facts
   can only measure factual recall. This one deliberately contains a superseded
   policy, a live contradiction between two offices, near-miss material that
   looks relevant and is not, and genuine silence.
2. **It must be reproducible from source.** The text lives here, not in a
   database dump, so anyone can regenerate the corpus and get identical results.
3. **Ground truth must be checkable by a string test.** Answers are short factual
   spans ("six months", "GT-4412"), so correctness is assessed without a judge
   model. Where judgement is unavoidable (abstention) the expectation is binary.

The domain is fictional university visa and travel policy. That choice is
deliberate: it is plausible, it naturally contains supersession and conflicting
offices, and it has no real-world sensitive content.
"""

from __future__ import annotations

from app.evaluation.dataset import (
    CaseCategory,
    EvalCase,
    EvalDataset,
    EvalDocument,
)

# --- corpus --------------------------------------------------------------

DOCUMENTS: tuple[EvalDocument, ...] = (
    EvalDocument(
        title="Visa Requirements",
        revision=1,
        # Current: passport, photograph and form rules are all still in force.
        # The original document also stated processing times and fees, but those
        # were withdrawn into a separate notice (below) so that each document
        # carries one status. Marking a whole document stale because one clause
        # changed is a modelling error, and it penalises any system that
        # correctly filters superseded material.
        information_status="current",
        content=(
            "Visa Requirements for International Travel\n\n"
            "All applicants travelling on an international itinerary must hold a "
            "passport that remains valid for at least six months beyond the "
            "intended date of return. A passport valid for fewer than six months "
            "will not be accepted at check-in.\n\n"
            "Applicants must submit a completed Form GT-4412 together with two "
            "passport photographs. Photographs must be taken within the previous "
            "six months and must show a plain white background."
        ),
    ),
    EvalDocument(
        title="Visa Processing Times (Withdrawn)",
        revision=1,
        # Withdrawn: superseded in full by the current notice. Kept in the
        # corpus and fully indexed, so the only thing hiding it is the retrieval
        # layer's status filter. That filter is what the H- cases measure.
        information_status="superseded",
        content=(
            "Visa Processing Times (Withdrawn Notice)\n\n"
            "This notice has been withdrawn. It formerly stated that applications "
            "are processed within fifteen working days of receipt, and that an "
            "expedited service reduces processing to five working days for an "
            "additional fee of 85 USD."
        ),
    ),
    EvalDocument(
        title="Visa Processing Times (Current)",
        revision=2,
        information_status="current",
        content=(
            "Visa Processing Times (Current Notice)\n\n"
            "This notice replaces the withdrawn processing notice. Applications "
            "are processed within twenty five working days of receipt.\n\n"
            "An expedited service is available and reduces processing to five "
            "working days. The expedited fee is 120 USD.\n\n"
            "The passport validity requirement is unchanged."
        ),
    ),
    EvalDocument(
        title="Travel Insurance Policy",
        revision=1,
        # Current. The Bulletin corrects one figure in it; that is a conflict to
        # resolve, not a superseded document, and conflating the two would let a
        # status filter hide the still-valid evacuation and claims rules.
        information_status="current",
        content=(
            "Travel Insurance Policy\n\n"
            "Travel insurance is mandatory for all international trips exceeding "
            "fourteen days in duration. Trips of fourteen days or fewer do not "
            "require insurance coverage.\n\n"
            "The policy covers medical expenses up to 250000 USD, emergency "
            "evacuation up to 100000 USD, and trip cancellation up to 5000 USD.\n\n"
            "Claims must be submitted within ninety days of the insured event. "
            "Late claims are refused without exception."
        ),
    ),
    EvalDocument(
        title="Insurance Office Bulletin",
        revision=1,
        content=(
            "Insurance Office Bulletin: Clarification of Cover\n\n"
            "Following enquiries, the Insurance Office clarifies that the medical "
            "expense limit under the travel insurance policy is 200000 USD, not "
            "250000 USD as stated in older guidance. All policies issued from the "
            "current academic year carry the 200000 USD limit.\n\n"
            "This clarification applies to medical expenses only. Emergency "
            "evacuation cover remains unchanged at 100000 USD."
        ),
    ),
    EvalDocument(
        title="Accommodation Guidance",
        revision=1,
        content=(
            "Student Accommodation Guidance\n\n"
            "On-campus accommodation is allocated on a first come, first served "
            "basis. Applications open on 1 April each year and close on 30 June.\n\n"
            "Each residence room includes a desk, a single bed, and a shared "
            "kitchen. Rooms are allocated in blocks of ten students to a shared "
            "kitchen facility.\n\n"
            "Requests for a specific residence block may be made in the "
            "application but cannot be guaranteed."
        ),
    ),
    EvalDocument(
        title="Library Services",
        revision=1,
        content=(
            "Library Services\n\n"
            "The library issues up to twelve borrowable items to a taught student "
            "at any one time. Research students may borrow up to twenty items.\n\n"
            "The standard loan period is twenty one days. Items may be renewed "
            "twice unless another reader has requested them.\n\n"
            "The library is silent and opening hours during term are 08:00 to "
            "23:00 on weekdays and 10:00 to 18:00 at weekends."
        ),
    ),
    EvalDocument(
        title="Course Registration",
        revision=1,
        content=(
            "Course Registration\n\n"
            "Students register for courses during a two week window that opens "
            "two weeks before the start of each semester.\n\n"
            "A standard full-time load is four courses per semester. Students may "
            "register for a maximum of five courses with the written approval of "
            "their academic adviser.\n\n"
            "Changing a course after the second week of teaching requires a "
            "completed amendment form GT-4412."
        ),
    ),
)

# --- cases ---------------------------------------------------------------
#
# `basis` records why each expectation follows from the corpus. It is required
# by the schema, so a future editor cannot add an unexplained expectation.

CASES: tuple[EvalCase, ...] = (
    # --- factual: one passage, stated plainly ----------------------------
    EvalCase(
        id="F-01",
        # A clear factual hit is the archetypal "should answer" case, so the
        # floor is fitted against it rather than against the cases it is later
        # reported on.
        split="calibration",
        category=CaseCategory.FACTUAL,
        question="How long must a passport remain valid beyond the return date?",
        relevant_titles=("Visa Requirements",),
        must_contain=("six months",),
        basis="Visa Requirements states 'at least six months beyond the intended date of return'.",
    ),
    EvalCase(
        id="F-02",
        category=CaseCategory.FACTUAL,
        question="Which form must visa applicants submit?",
        relevant_titles=("Visa Requirements",),
        must_contain=("GT-4412",),
        basis="Visa Requirements names Form GT-4412 as mandatory.",
    ),
    EvalCase(
        id="F-03",
        category=CaseCategory.FACTUAL,
        question="How many items may a taught student borrow from the library?",
        relevant_titles=("Library Services",),
        must_contain=("twelve",),
        basis="Library Services states taught students may borrow up to twelve items.",
    ),
    EvalCase(
        id="F-04",
        split="calibration",  # Second factual case so the floor is not fitted to a single document.
        category=CaseCategory.FACTUAL,
        question="What is the standard loan period for library items?",
        relevant_titles=("Library Services",),
        must_contain=("twenty one days",),
        basis="Library Services gives the standard loan period as twenty one days.",
    ),
    EvalCase(
        id="F-05",
        category=CaseCategory.FACTUAL,
        question="How many courses is a standard full-time load per semester?",
        relevant_titles=("Course Registration",),
        must_contain=("four",),
        basis="Course Registration states a standard full-time load is four courses.",
    ),
    # --- precision: a number that is easy to garble -----------------------
    EvalCase(
        id="P-01",
        category=CaseCategory.PRECISION,
        question="What is the maximum medical expense cover under the travel insurance policy?",
        # The correct figure appears only in the Bulletin. The Policy is the
        # distractor that states the outdated 250000.
        relevant_titles=("Insurance Office Bulletin",),
        must_contain=("200000",),
        must_not_contain=("250000",),
        basis=(
            "The Insurance Office Bulletin explicitly corrects the medical limit to "
            "200000 USD and says older guidance stating 250000 is out of date. An "
            "answer of 250000 is the documented error this case exists to catch."
        ),
    ),
    EvalCase(
        id="P-02",
        category=CaseCategory.PRECISION,
        question="What is the emergency evacuation cover limit?",
        relevant_titles=("Travel Insurance Policy",),
        must_contain=("100000",),
        basis=(
            "Travel Insurance Policy sets evacuation at 100000 USD and the Bulletin "
            "states evacuation cover is unchanged."
        ),
    ),
    EvalCase(
        id="P-03",
        split="calibration",  # A numeric answer, to check the floor does not require a high score.
        category=CaseCategory.PRECISION,
        question="Within how many days must an insurance claim be submitted?",
        relevant_titles=("Travel Insurance Policy",),
        must_contain=("ninety",),
        basis="Travel Insurance Policy requires claims within ninety days.",
    ),
    EvalCase(
        id="P-04",
        category=CaseCategory.PRECISION,
        question="When do accommodation applications close each year?",
        relevant_titles=("Accommodation Guidance",),
        must_contain=("30 June",),
        basis="Accommodation Guidance gives the closing date as 30 June.",
    ),
    # --- superseded: the current value differs from the original ----------
    EvalCase(
        id="S-01",
        category=CaseCategory.SUPERSEDED,
        question="How long do visa applications currently take to process?",
        relevant_titles=("Visa Processing Times (Current)",),
        must_contain=("twenty five",),
        must_not_contain=("fifteen",),
        basis=(
            "Updated Visa Processing Times supersedes the original fifteen working "
            "days with twenty five. Answering fifteen is a supersession failure."
        ),
    ),
    EvalCase(
        id="S-02",
        category=CaseCategory.SUPERSEDED,
        question="What is the current expedited visa fee?",
        relevant_titles=("Visa Processing Times (Current)",),
        must_contain=("120",),
        must_not_contain=("85",),
        basis="The notice raises the expedited fee from 85 USD to 120 USD.",
    ),
    # --- historical: the OLD value is the correct answer ------------------
    EvalCase(
        id="H-01",
        category=CaseCategory.HISTORICAL,
        question="What was the expedited visa fee before it was increased?",
        relevant_titles=("Visa Processing Times (Withdrawn)",),
        must_contain=("85",),
        basis=(
            "Both notices together record 85 USD as the prior fee. This case "
            "distinguishes 'retrieve the current value' from 'retrieve the history', "
            "which a naive latest-only system cannot do."
        ),
        notes=(
            "Requires include_superseded to be reachable; a failure here is "
            "informative, not disqualifying."
        ),
    ),
    EvalCase(
        id="H-02",
        category=CaseCategory.HISTORICAL,
        question="What processing time applied before the revised notice?",
        relevant_titles=("Visa Processing Times (Withdrawn)",),
        must_contain=("fifteen",),
        basis="The original Visa Requirements states fifteen working days.",
        notes="Same caveat as H-01.",
    ),
    # --- multi-source ----------------------------------------------------
    EvalCase(
        id="M-01",
        category=CaseCategory.MULTI_SOURCE,
        question=(
            "A trip lasts thirty days. Is travel insurance required, and how long "
            "must a passport be valid?"
        ),
        relevant_titles=("Travel Insurance Policy", "Visa Requirements"),
        # "mandatory"/"required" are both correct readings of the insurance rule,
        # so the check accepts either rather than penalising wording.
        must_contain=("six months",),
        basis=(
            "Insurance Policy makes cover mandatory above fourteen days, so a "
            "thirty-day trip requires it; Visa Requirements gives the passport rule. "
            "Neither document alone answers both halves."
        ),
    ),
    EvalCase(
        id="M-02",
        category=CaseCategory.MULTI_SOURCE,
        question="Which form is needed both for a visa application and for changing a course?",
        relevant_titles=("Visa Requirements", "Course Registration"),
        must_contain=("GT-4412",),
        basis="Both documents name Form GT-4412, in different contexts.",
    ),
    # --- conflicting -----------------------------------------------------
    EvalCase(
        id="C-01",
        category=CaseCategory.CONFLICTING,
        question="According to older guidance, what was the medical expense limit?",
        relevant_titles=("Travel Insurance Policy",),
        must_contain=("250000",),
        basis=(
            "Travel Insurance Policy states 250000 and the Bulletin calls it 'older "
            "guidance'. Asking explicitly for the older figure separates 'can find "
            "the superseded text' from 'confuses it with the current value'."
        ),
    ),
    # --- unanswerable: the only correct behaviour is abstention ----------
    EvalCase(
        id="U-01",
        # An unanswerable case is essential to calibration: without one, any floor appears perfect.
        split="calibration",
        category=CaseCategory.UNANSWERABLE,
        question="What is the university's policy on emotional support animals in residences?",
        relevant_titles=(),
        expect_abstention=True,
        basis="No document mentions animals in any form.",
    ),
    EvalCase(
        id="U-02",
        # Second unanswerable case: one wording could be tuned to by accident.
        split="calibration",
        category=CaseCategory.UNANSWERABLE,
        question="How much does a parking permit for the campus cost?",
        relevant_titles=(),
        expect_abstention=True,
        basis="No document discusses parking or permits.",
    ),
    EvalCase(
        id="U-03",
        category=CaseCategory.UNANSWERABLE,
        question="What is the deadline for submitting the final dissertation?",
        relevant_titles=(),
        expect_abstention=True,
        basis="No document mentions dissertations or submission deadlines.",
    ),
    # --- near miss: related vocabulary, no answer ------------------------
    EvalCase(
        id="N-01",
        category=CaseCategory.NEAR_MISS,
        question=(
            "How many items may a research student borrow from the library for a residence kitchen?"
        ),
        relevant_titles=("Library Services",),
        must_contain=("twenty",),
        must_not_contain=("twelve",),
        basis=(
            "The question mixes two documents to test whether the right distinction "
            "is made: research students may borrow twenty, taught students twelve. "
            "Answering twelve for a research student is a precision failure."
        ),
    ),
    EvalCase(
        id="N-02",
        # Near-miss: must still retrieve the visa documents, and must not
        # pretend a standard fee exists.
        split="calibration",
        category=CaseCategory.NEAR_MISS,
        question="What fee applies to a visa application that is not expedited?",
        relevant_titles=("Visa Requirements", "Visa Processing Times (Current)"),
        must_contain=("no",),
        basis=(
            "Neither document states a standard application fee; they mention only "
            "the expedited surcharge. A system that invents a base fee fails this "
            "case, and so does one that reports the surcharge as the total."
        ),
        notes="Acceptable answers must indicate that no standard fee is stated.",
    ),
    # --- ambiguous -------------------------------------------------------
    EvalCase(
        id="A-01",
        category=CaseCategory.AMBIGUOUS,
        question="How long does processing take?",
        relevant_titles=("Visa Processing Times (Current)",),
        must_contain=("working days",),
        basis=(
            "Which process is unspecified. The corpus only gives visa processing "
            "times, so the answer must address visa processing or say which process "
            "it refers to; it must not silently answer about, say, library requests."
        ),
    ),
)

DATASET = EvalDataset(
    name="mnemos-university-policy",
    version="1.0.0",
    documents=DOCUMENTS,
    cases=CASES,
    description=(
        "Synthetic university policy corpus with matched questions across factual, "
        "precision, supersession, historical, multi-source, conflicting, "
        "unanswerable, near-miss and ambiguous categories."
    ),
    metadata={
        "domain": "university visa and student services policy",
        "language": "en",
        "ground_truth_style": "substring match, no judge model",
        "why_synthetic": (
            "Synthetic text is redistributable, so the dataset can ship with the "
            "repository and the evaluation stays reproducible by a third party."
        ),
    },
)


__all__ = ["CASES", "DATASET", "DOCUMENTS"]
