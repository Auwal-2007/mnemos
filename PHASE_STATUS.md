# MNEMOS — Phase Status

**Updated:** 2026-11-16
**Rule:** a phase is VERIFIED only when its behaviour was executed and observed.
Anything requiring a live provider or a host is BLOCKED, with the reason named.

Status vocabulary: `NOT STARTED` · `IN PROGRESS` · `IMPLEMENTED` · `TESTED` ·
`VERIFIED` · `BLOCKED`.

`TESTED` means covered by tests that execute. `VERIFIED` means observed working
against the real dependency (a live model, a live database, a browser).

---

## Phase status table

| Phase | Deliverable | Status | Evidence |
|---|---|---|---|
| 0 | Reconciliation | **VERIFIED** | `COMPLETION_AUDIT.md`, this file |
| 1A–1C | Foundation, schema, shell | **VERIFIED** | 221 migration checks; earlier reports |
| 2A | Provenance schema | **VERIFIED** | migrations + RLS checks |
| 2B | Ingestion | **TESTED** | 77 ingestion tests |
| 2C | Chunking, embeddings, index | **TESTED** | local Postgres + fake provider |
| 3A | Hybrid retrieval | **TESTED** | 21 service + 14 API tests |
| 3B | Grounded generation | **TESTED** | 24 unit + 20 API tests, fake provider |
| 3C | Verification & memory | **TESTED** | 38 unit + 4 real-PostgreSQL |
| 3D | Agents & orchestration | **TESTED** | 29 + 14 provider tests |
| 4A | Evaluation framework | **VERIFIED** | real PostgreSQL, 22 cases, calibrated |
| 4A-live | Model/embedding metrics | **BLOCKED** | no provider egress |
| 4A-gate | Evidence floor calibrated, held-out | **VERIFIED** | 0.25; acc 0.750 held-out |
| 4B | Comparative / robustness | **IN PROGRESS** | lexical-side comparisons only |
| 4C | Reproducibility & report | **IN PROGRESS** | runner + report generator |
| 5A | Frontend API integration | **NOT STARTED** | — |
| 5B | Product experience | **NOT STARTED** | — |
| 5C | End-to-end validation | **BLOCKED (part)** | no browser |
| 6A | Security hardening | **NOT STARTED** | — |
| 6B | Performance & reliability | **NOT STARTED** | — |
| 6C | Live integration & deploy | **BLOCKED** | network + credentials |
| 7A | System audit | **NOT STARTED** | — |
| 7B | Release quality | **NOT STARTED** | — |
| 7C | Product delivery | **NOT STARTED** | — |

---

## The boundary that will not move

Three capabilities are requested and **cannot be delivered in this
environment**, for reasons outside the code:

1. **Live model verification.** `api.openrouter.ai` is unreachable from this
   sandbox (verified by connection attempt). No key exists.
2. **Live Supabase verification.** `*.supabase.co` is unreachable. No project.
3. **Browser-rendered verification.** Chromium cannot be downloaded here.

Everything that does not depend on those is completed and run. Where a metric
needs a model, the harness is built and executed against a *recorded fake
provider* so the pipeline is proven end-to-end, and the result is labelled
**pipeline-verified, not model-verified**. It is never reported as a real
quality measurement.

---

## §4A Evaluation — detail

| Item | Status |
|---|---|
| Dataset schema + versioning | **VERIFIED** — schema rejects an unexplained expectation |
| Seeded corpus (deterministic) | **VERIFIED** — 8 docs, seeded through the real chunker |
| Question set across all required categories | **VERIFIED** — 22 cases, 9 categories |
| Retrieval metrics (Recall@K, Precision@K, MRR, nDCG) | **VERIFIED** — 26 unit tests |
| Citation precision/recall | **VERIFIED** |
| Abstention metrics | **VERIFIED** — floor calibrated on a held-out split |
| Baseline RAG implementation | **VERIFIED** — shares corpus, k and query parsing |
| Reproducible runner + recorded config | **VERIFIED** — determinism asserted by test |
| Report generator | **VERIFIED** — `eval-results/final/report.md` |
| Model-dependent metrics | **BLOCKED** (no provider egress) |

### Reported results, including the ones that do not flatter MNEMOS

| Metric | MNEMOS | +history | Baseline |
|---|---|---|---|
| Recall@5 | 0.842 | 0.947 | **1.000** |
| Precision@5 | **0.402** | 0.392 | 0.286 |
| MRR | 0.816 | 0.868 | **0.895** |

The baseline leads on recall and MRR. MNEMOS leads on precision. Supersession
filtering costs recall by design; enabling history recovers most of it. There is
no aggregate score, and no claim that MNEMOS retrieves better overall.

Two negative findings are recorded rather than buried: lexical strength cannot
separate answerable from unanswerable questions (§6.4 of `docs/EVALUATION.md`),
and the ADR-0012 thresholds remain uncalibrated for want of labelled verdicts.
