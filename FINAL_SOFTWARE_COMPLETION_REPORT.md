# MNEMOS — Final Software Completion Report

**Date:** 2026-11-16
**Branch:** `arena/1ee787c5-mnemos`
**Scope:** software only. No academic chapters, no DOCX, no slides.

---

## 1. Summary in one paragraph

The repository already had a working, well-tested backend for Phases 2–3 and a
frontend that was visually complete but **disconnected from it**. This session
found and fixed a retrieval defect that made the system refuse to answer
three-quarters of answerable questions, built the evaluation framework that had
never existed (and which is how that defect was found), connected the frontend to
conversations, retrieval, memory and agents, removed interface copy that had
become false, and added rate limiting. It did **not** deploy anything, and no live
model or hosted database was ever contacted, because both are unreachable from
this environment. Those gaps are stated below rather than papered over.

## 2. What was already working (not rebuilt)

| Area | State at session start |
|---|---|
| Schema, 23 tables, RLS forced | Verified by 221 assertions |
| Ingestion, chunking, embeddings (logic) | 77 tests |
| Hybrid retrieval (RRF) | 21 service + 14 API tests |
| Grounded generation, citation validation | 24 unit + 20 API tests |
| Verification, corrections, conflicts | 38 unit + 4 real-PostgreSQL |
| Four agent roles, orchestration traces | 29 + 14 tests |
| Frontend shell, design system, auth | 119 tests |

Nothing here was rewritten. The work below is additive or corrective.

## 3. What was incomplete, and what was done

### 3.1 Phase 4A evaluation did not exist

No dataset, no metrics, no baseline, no runner, no results. Built in full:
schema with enforced ground-truth justification and content fingerprinting; an
8-document, 22-case corpus across nine behavioural categories; metrics defined
before implementation; a real-PostgreSQL harness that applies every migration and
seeds through the production chunker; a conventional RAG baseline sharing corpus,
`k` and query parsing; a reproducible CLI writing results, dataset and a generated
report; calibration on a held-out split.

### 3.2 A P1 retrieval defect

`websearch_to_tsquery` joins every term with AND, so a natural question required
all of its words in one chunk.

**Measured:** 73.7% of answerable cases returned **no evidence**. Because
generation may not answer without evidence, this surfaced to users as refusal.

**Fixed** in migration `20260104000000`: match strictly first, relax to term-OR
only when the conjunction matches nothing. Recall@5 0.211 → 0.605, MRR 0.263 →
0.789 on the corpus as it then stood. Regression test added.

### 3.3 The frontend was not connected

Built typed clients for conversations, messages, answers, verification, retrieval,
memory and agents; hooks following the existing conventions; an `AnswerView` that
distinguishes answered/abstained/degraded and makes every citation open its real
provenance record; connected orchestrator and direct-specialist pages; a memory
workspace for corrections, revisions and conflicts; `EvidencePanel` finally
consumed; claim verification run automatically after each answer.

### 3.4 The interface stated things that were false

It told users agents were "not connected to a model", that "no model execution or
orchestration exists yet", and that specialists were "planned". All three became
false in Phases 3B–3D and were still on screen, including in the agent catalogue,
the navigation, the dashboard, the landing page, the conversations index and the
OpenAPI description. Corrected everywhere, with regression tests that fail if the
old text returns.

### 3.5 No rate limiting

Added a fixed-window limiter bucketed by verified token subject, with health
probes exempt and the in-process limitation documented. Seven tests.

## 4. Tests executed

| Suite | Result |
|---|---|
| Backend `pytest` | **487 passed** (was 442) |
| Migration + RLS assertions | **223 passed, 0 failed** (was 221) |
| `ruff check` / `format` | Clean |
| `mypy app` | Clean, 74 files |
| Frontend `vitest` | **142 passed** (was 119) |
| `tsc --noEmit` | Clean |
| `npm run build` | Passed — entry 163 kB, vendor 393 kB, three 472 kB lazy |
| Evaluation run | Completes; artefacts in `backend/eval-results/final/` |

New tests this session: 45 backend (26 evaluation, 12 evaluation-live, 7 rate
limit), 23 frontend (13 API contracts, 9 answer rendering, plus rewritten
conversation-mode tests).

## 5. Measured results, including the unflattering ones

Retrieval, lexical-only, 22 cases, real PostgreSQL:

| Metric | MNEMOS | +history | Baseline |
|---|---|---|---|
| Recall@5 | 0.842 | 0.947 | **1.000** |
| Precision@5 | **0.402** | 0.392 | 0.286 |
| MRR | 0.816 | 0.868 | **0.895** |
| nDCG@5 | 0.823 | 0.885 | **0.918** |

**The conventional baseline outperforms MNEMOS on recall, MRR and nDCG.** MNEMOS
leads only on precision, which is the expected cost of hiding superseded material
by default. Enabling history recovers most of the gap. This is reported as a
negative result; no case was adjusted to reverse it.

Two further negative findings:

1. **Lexical strength cannot judge evidence sufficiency.** An answerable question
   scored `ts_rank_cd` 0.011 while an unanswerable one scored 0.100. No threshold
   separates them, so the calibrated floor (0.25) eliminates missed abstentions
   but refuses ~27% of answerable questions.
2. **ADR-0012's 0.70/0.45 boundaries are uncalibrated.** They were chosen by
   judgement, never tested against adjudicated verdicts, and no such labels exist.
   They are now configurable and are documented as defaults, not results.

## 6. Live integration results

**None. Zero.** No model call, no embedding call, no hosted-database query has
ever executed.

Measured cause: `api.openrouter.ai`, `openrouter.ai` and `db.supabase.co` all fail
to connect from this sandbox, while `github.com`, `registry.npmjs.org` and
`pypi.org` respond. No credentials exist in the environment either.

This is not a code defect and it is not hidden: the affected metrics appear under
`blocked_metrics` in `results.json`, and `REQUIREMENTS_TRACEABILITY.md` records
zero requirements at evidence level L5.

## 7. Deployment status

**Not deployed.** No host, no domain, no production database. `docs/DEPLOYMENT.md`
is a configuration guide whose first line says so. CI (four jobs) runs on every
pull request and passes; that is real, and it is the only thing at end-to-end
evidence level.

## 8. Security findings

Implemented and tested: JWT verification; RLS on all 23 tables with forced
row-level security; explicit membership checks producing `403` rather than empty
results; instruction/data separation in both generation and verification prompts;
no tool access reachable from retrieved content; citation validation; server-side
upload validation; a database trigger blocking self-approval of corrections;
secrets confined to the backend with a CI hygiene job; rate limiting; per-request
timeouts.

**Not tested:** malicious uploaded documents (parsing is in-process and
unsandboxed — a real residual risk), prompt injection against a live model, and
any penetration test. No audit was performed. The absence of a finding in
`docs/SECURITY.md` means a control was tested and held, or that no test was run —
never that the system is secure in general.

## 9. Performance observations

Retrieval p50 is single-digit milliseconds locally on 8 documents, measured by the
evaluation harness. Frontend bundle: 163 kB entry (43 kB gzip), with `three` at
472 kB deferred behind a lazy boundary.

**No load test was run.** There are no throughput figures for concurrent users,
and none should be inferred from the latency numbers.

## 10. Remaining blockers

| Blocker | Exact action required |
|---|---|
| No live OpenRouter | Set `OPENROUTER_API_KEY` and model ids in a network-enabled environment; run the checklist in `docs/DEPLOYMENT.md` §7 |
| No live Supabase | Supply `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`; confirm `pgvector` is available; apply 11 migrations |
| No embeddings verified | Set `EMBEDDING_*`; make one real call and read the actual vector length before trusting `EMBEDDING_DIMENSION` |
| No deployment | Choose hosts, set env, deploy, then verify each item in §7 of the deployment guide |
| No browser E2E | Install a browser runtime; the nine journeys need Playwright or equivalent |

## 11. Known limitations

Nineteen entries in `KNOWN_ISSUES.md`, each with its evidence. The ones that
matter most:

- Answer quality is entirely unmeasured (no model).
- The baseline wins on recall.
- ~27% of answerable questions are refused by the calibrated floor.
- Semantic retrieval has never executed; every retrieval figure is a lexical
  floor.
- No streaming (deliberately not simulated).
- Ingestion has no durable job state; a restart mid-index needs a manual re-run.
- No notifications, no cost accounting, no CVE audit.

## 12. Verification summary

| Level | Count |
|---|---|
| Integration-tested against real PostgreSQL | 41 |
| Unit-tested against fakes | 38 |
| Implemented, untested | 8 |
| End-to-end (CI pipeline itself) | 1 |
| **Live-provider verified** | **0** |
| **Production-verified** | **0** |

The honest headline: the system is well tested *up to the boundary of this
environment*, and nothing beyond that boundary has been observed. Every claim in
this report is traceable to a test run or a document in the repository. Where the
work fell short, that is written down rather than omitted.
