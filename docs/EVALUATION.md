# Evaluation (Phase 4A)

This document describes how MNEMOS measures itself: the dataset, the metrics and
their exact definitions, the systems compared, the calibration procedure, the
results obtained, and — importantly — what could not be measured and why.

Every number in this file comes from `python -m app.evaluation.run`. None was
transcribed by hand. The run artefacts are written to `backend/eval-results/`.

---

## 1. Reproducing a run

```bash
cd backend
python -m app.evaluation.run --label my-run
```

Artefacts per run, in `backend/eval-results/<label>/`:

| File | Contents |
|---|---|
| `results.json` | Manifest, per-case outcomes, aggregate metrics, blocked metrics |
| `dataset.json` | The exact corpus and questions used |
| `report.md` | Generated Markdown report |

The evaluation **requires real PostgreSQL** (via `pgserver`). This is deliberate:
a mocked search would measure the mock. Every migration is applied in order and
the corpus is seeded through the production chunker, so what is measured is the
SQL function and indexes that ship.

---

## 2. Dataset

`app/evaluation/corpus.py` — dataset `mnemos-university-policy` v1.0.0.

8 synthetic documents, 22 questions, 9 behavioural categories. The domain is
fictional university visa and student-services policy: plausible, naturally
contains supersession and inter-office contradiction, and free of real-world
sensitive content.

Synthetic text is used because it is redistributable. A dataset that cannot ship
with the repository cannot be reproduced by a third party, and an unreproducible
evaluation is an assertion.

### Case categories

| Category | Cases | What a failure means |
|---|---|---|
| `factual` | 5 | Retrieval misses a plainly stated fact |
| `precision` | 4 | A number or date is garbled, or a corrected figure is not preferred |
| `superseded` | 2 | A withdrawn value is returned as current |
| `historical` | 2 | Withdrawn material is unreachable when explicitly asked for |
| `multi_source` | 2 | Evidence from two documents is not combined |
| `conflicting` | 1 | An older figure is confused with the current one |
| `unanswerable` | 3 | The system answers when the corpus is silent |
| `near_miss` | 2 | Related vocabulary is treated as an answer |
| `ambiguous` | 1 | An underspecified question is answered without qualification |

### Ground truth is checkable without a judge

Each case declares `must_contain` / `must_not_contain` substrings and the `basis`
for the expectation. The schema *rejects* a case with no recorded basis, and a
test asserts that every required string actually appears in the corpus. That
check caught a real flaw: case `M-01` required the word "required" when the
source says "mandatory", so a correct answer would have failed.

### Calibration / evaluation split

6 cases are `calibration`, 16 are `evaluation`. Any number that has to be chosen
(a threshold, a floor) is chosen on the calibration split only. The evaluation
split is never inspected while choosing, so the reported performance is not the
performance of a value fitted to it.

---

## 3. Systems compared

| System | Retrieval | Supersession | Fusion |
|---|---|---|---|
| `mnemos` | Hybrid RRF through `hybrid_search_chunks` | Superseded excluded | Yes (RRF, k=60) |
| `mnemos_history` | Same, `include_superseded = true` | Included | Yes |
| `baseline` | One retriever, plain top-k by `ts_rank_cd` | Not modelled — sees everything | No |

### The baseline is not a straw man

It uses the same corpus, the same chunking, the same `k`, the same PostgreSQL
instance, and **the same query parser**. Query parsing is shared deliberately: if
the baseline parsed questions differently it would lose for a reason unrelated to
pipeline architecture, and the comparison would be worthless.

The baseline is given the *relaxed* parse unconditionally, which is marginally
more permissive than MNEMOS's strict-first parsing. If that asymmetry helps
anyone, it helps the baseline.

The real architectural differences are: RRF fusion of a wider candidate pool,
provenance identity on every passage, and a supersession model. Those are what
the comparison measures.

---

## 4. Metric definitions

| Metric | Definition |
|---|---|
| **Recall@K** | Fraction of ground-truth relevant documents in the top K passages. A document counts once however many passages it contributes. Undefined when no document is relevant, and such cases are excluded from the mean. |
| **Precision@K** | Fraction of the top K passages whose document is relevant. Defined as 0 when nothing is relevant — returning passages for an unanswerable question is a real behaviour and is penalised. |
| **MRR** | Reciprocal rank of the first relevant passage; 0 if none. Undefined for unanswerable cases. |
| **nDCG@K** | Binary-gain discounted cumulative gain normalised by the ideal ordering. |
| **Citation precision** | Of the documents retrieved (the citations an answer would carry), the fraction that are relevant. |
| **Citation recall** | Of the relevant documents, the fraction retrieved. |
| **Abstention accuracy** | 1 when the system produced evidence exactly when evidence exists, else 0, averaged over all cases. |
| **False abstention** | Among answerable cases, the fraction with no evidence returned. |
| **Missed abstention** | Among unanswerable cases, the fraction where evidence *was* returned. |

Two deliberate design choices:

**Undefined is not zero.** `mean()` returns `None` for an empty set, and the
report prints `—`. A metric with no applicable cases is unmeasured; printing
`0.000` would read as total failure and drag the reader to a false conclusion.

**Recall and precision treat unanswerable cases differently.** Recall excludes
them; precision scores them 0. This is intentional: flooding the context on a
question the corpus cannot answer is a failure worth seeing.

**There is no composite score.** A weighted headline number would let a strong
factual score hide a broken abstention. Per-category tables are reported instead.

---

## 5. Results

### 5.1 What is measured

With no embedding provider reachable, **all three systems ran lexically**. The
comparison is therefore of pipeline architecture, not of hybrid versus dense
retrieval. Recall figures here are a floor for a hybrid deployment, not an
estimate of it.

### 5.2 Run: `fair-baseline` (corpus v1.0.0, 22 cases, 8 documents)

| Metric | MNEMOS (current only) | MNEMOS (+ history) | Baseline RAG |
|---|---|---|---|
| Recall@1 | 0.711 | 0.711 | 0.711 |
| Recall@3 | 0.842 | 0.947 | 1.000 |
| Recall@5 | 0.842 | 0.947 | 1.000 |
| Precision@5 | **0.402** | 0.392 | 0.286 |
| MRR | 0.816 | 0.868 | 0.895 |
| nDCG@5 | 0.823 | 0.885 | 0.918 |
| Citation precision | **0.402** | 0.392 | 0.286 |
| Citation recall | 0.842 | 0.947 | 1.000 |
| Abstention accuracy | 0.000 | 0.000 | 0.000 |
| False abstention | 0.000 | 0.000 | 0.000 |

### 5.3 Honest reading of these numbers

**The baseline wins on recall, MRR and nDCG. MNEMOS wins on precision.** This is
a negative result for MNEMOS and it is reported as such.

The mechanism is visible in the per-case data: the baseline never filters, so it
always retains the withdrawn notice that answers the historical questions.
MNEMOS's default configuration correctly hides withdrawn material, which costs it
recall on the two `historical` cases by design — and `mnemos_history` recovers
most of the gap (0.842 → 0.947), which is exactly what that configuration exists
to demonstrate.

So the defensible claim is narrow: **supersession filtering buys precision at the
cost of recall, and reachable history recovers the recall.** It is not a claim
that MNEMOS retrieves better overall. On this corpus it does not.

**Abstention accuracy is 0.000 for every system.** No system distinguishes "the
corpus is silent" from "the corpus says something vaguely related". Section 6 is
about that.

---

## 6. Calibration

### 6.1 The problem the calibration exposed

An earlier run surfaced a severe defect: **73.7% of answerable questions returned
no evidence at all.** The cause was `websearch_to_tsquery`, which joins every
term with AND, so a natural question required all six of its words in one chunk.

Migration `20260104000000_retrieval_query_relaxation.sql` fixed it: match strictly
first, fall back to a term-OR parse only when the conjunction matches nothing.

Measured effect on the same corpus:

| Metric | Before | After |
|---|---|---|
| Recall@5 (MNEMOS) | 0.211 | 0.605 |
| MRR (MNEMOS) | 0.263 | 0.789 |
| False abstention (MNEMOS) | 0.737 | 0.053 |

(The absolute figures moved again when the corpus was later corrected — see
§6.4 — but the direction and magnitude of the fix are these.)

That fix bought recall and cost the abstention signal: with terms OR-ed together,
almost any question matches something. Hence the need for a threshold.

### 6.2 Procedure

Sweep a floor on the retriever's own strength (`ts_rank_cd` of the best matching
passage) across a fixed grid, score each on the **calibration split only**, take
the best, then report it on the held-out split.

`ts_rank_cd` is used rather than the fused RRF score because RRF deliberately
discards magnitude — that is what makes it robust across retrievers, and also
what makes it useless for asking "was this a strong match or a stray common
word?".

The grid is fixed in advance (0.0 → 0.8) rather than searched finely, so the
chosen value is one of a small, stateable set. Ties are broken toward the **lower**
floor: of two equally accurate thresholds, the one that abstains less is
preferred, because a spurious refusal is visible to the user while an over-eager
answer can at least be inspected against its citations.

### 6.3 Result

Chosen on calibration: **floor = 0.25** (plateau 0.25–0.50, all equal on
calibration).

Held-out evaluation split (never used to choose the floor):

| Metric | Value |
|---|---|
| Abstention accuracy | 0.750 |
| False abstention | 0.267 |
| Missed abstention | 0.000 |

### 6.4 The negative finding that matters

**Lexical strength is not an adequate evidence-sufficiency signal.** The measured
strengths show why:

| Case | Should abstain? | Best `ts_rank_cd` |
|---|---|---|
| `F-01` "how long must a passport remain valid" | no | 1.300 |
| `P-03` "how many days to submit a claim" | no | 1.200 |
| `N-02` "fee for a non-expedited visa" | no | 0.500 |
| `U-01` "emotional support animals in residences" | **yes** | 0.200 |
| `U-02` "cost of a parking permit" | **yes** | 0.100 |
| `F-04` "standard loan period" | no | **0.011** |

`F-04` is a genuine, answerable question whose best match scores *below* an
unanswerable one. No single threshold separates these populations. The 0.25 floor
therefore eliminates missed abstentions entirely at the cost of refusing a quarter
of answerable questions.

This is not a tuning failure to be fixed by a better grid. It is a property of
lexical overlap: "standard loan period" has few distinctive terms, while
"residences" matches "residence" strongly in an unrelated document.

The honest conclusion is that evidence sufficiency needs a **semantic** signal
(embedding similarity between question and passage) or a model judgement, and
neither is available in this environment. The floor of 0.25 is the best available
cut-off on an inadequate signal, and must be re-derived once embeddings are
configured.

### 6.5 The 0.70 / 0.45 verification thresholds

`app/services/verification.py` decides claim support from lexical overlap, with
boundaries at 0.70 (supported) and 0.45 (below this, unsupported).

**Origin:** fixed by judgement when the method was written. They were not derived
from labelled data, and no labelled set of claim verdicts exists in this
repository.

**Status: not calibrated.** Calibrating them would need claims with
human-adjudicated support labels. None exist, and generating them would be human
review rather than automated evaluation. Claiming 0.70 is a validated boundary
would overstate what is known.

**What was done instead:**
- Both boundaries are now a validated, configurable `VerificationThresholds`
  object (`0 <= unsupported_below < supported_at <= 1` is enforced), so a
  deployment can change the policy without editing code and cannot accidentally
  make `partially_supported` unreachable.
- Their status is stated in `docs/adr/0012-verification-policy.md`.

They remain defaults, not results.

---

## 7. What was NOT measured, and why

| Metric | Why not |
|---|---|
| Answer correctness | Requires a generation model. No provider is reachable (`api.openrouter.ai` is network-blocked here). |
| Faithfulness | Same. |
| Claim-level attribution | Requires generation **and** verification against a model. |
| Unsupported-answer rate | Same. |
| Token usage | Requires a provider response. |
| Estimated cost | Requires provider billing data. Never estimated from assumption. |
| Semantic retrieval quality | Requires an embedding provider. |
| Hybrid vs lexical | Same. |
| Human review | **None occurred.** No case was adjudicated by a person. Expectations were authored with the corpus and are visible in `dataset.json` for inspection. No inter-annotator agreement can be reported because there was only one author. |

These appear in `results.json` under `blocked_metrics` with their reasons, so a
reader of the raw artefact sees them too.

---

## 8. Limitations

1. **Lexical-only.** Every figure here is a floor for a hybrid deployment.
2. **22 cases.** Enough to expose categorical failures; not enough to estimate a
   stable population parameter. Differences of a few hundredths are noise. No
   confidence intervals are reported because the sample does not support them.
3. **Single author, no human review.** Ground truth reflects one person's reading
   of the corpus.
4. **Substring ground truth.** A correct answer phrased unusually could fail a
   `must_contain` check. This under-reports correctness; it cannot over-report it.
5. **Corpus revised once.** An early version marked whole documents superseded
   when only part of their content was stale, which unfairly penalised status
   filtering. The revision is recorded in §6.1 and in the changelog; the
   correction made the ground truth accurate, not easier — recall rose for
   `mnemos` but the baseline still leads on it.
6. **No answer-level evaluation at all.** The largest gap. Retrieval metrics say
   nothing about whether a generated answer would be faithful.

---

## 9. Next steps for evaluation (blocked here)

1. Configure an embedding provider → measure semantic and hybrid retrieval, and
   re-derive the evidence floor on the semantic signal.
2. Configure a chat model → measure answer correctness, faithfulness and
   claim-level attribution; build the RAG baseline's answer path for a true
   end-to-end comparison.
3. Grow the dataset, and have a second person independently label a subset so
   agreement can be reported.
