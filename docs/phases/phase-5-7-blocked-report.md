# Phases 5–7 — Audit and Blocked-Execution Report

**Date:** 2026-11-15
**Branch:** `arena/1ee787c5-mnemos` (base `38da949`)
**Verdict:** Phases 5, 6 and 7 **cannot be executed as specified**. This
document records the audit that establishes that, and exactly what would
unblock each phase.

This is not a refusal to work. It is the audit the prompt explicitly demands
("Do not assume that previous AI-generated completion reports prove that
functionality exists... Inspect the actual repository and verify implementation
before proceeding"). The inspection found a precondition failure, and the
prompt's own rule applies: *"Do not proceed past a critical failure."*

---

## 1. Precondition check

The prompt states: *"Phases 2, 3 and 4 must already have been implemented or
their actual completion status established."*

| Phase | Actual status | Evidence |
|---|---|---|
| 0 — Foundation | Complete | reports, ADRs, CI |
| 1A/1B/1C — Infra, schema, shell | Complete | 126 migration checks, 35 authz tests |
| 2A — Provenance schema | Complete | migration + tests |
| 2B — Ingestion | Complete | 77 ingestion tests |
| 2C — Chunking + vectors | Complete | 20+22+15 tests, 126 checks |
| UI redesign | Complete | 119 frontend tests, axe 0 |
| **3 — Retrieval, generation** | **Absent** | no code, no schema, no tests |
| **4 — Verification, memory, agents, evaluation** | **Absent** | no code, no schema, no tests |

Verified by direct inspection:

```
backend/app/          → 44 source files; no retrieval, no LLM client,
                        no agent, no prompt, no evaluation module
supabase/migrations/  → 11 tables; none for conversations, messages,
                        answers, claims, verification, memory revisions,
                        conflicts
API surface           → 25 routes; none for ask/retrieve/generate/verify
requirements.txt      → no LLM SDK beyond httpx (no adapter written)
docs/                 → no phase-3 or phase-4 report exists
```

Baseline re-verified before drawing this conclusion:

```
backend pytest        247 passed (5 skipped without pgserver)
frontend vitest       119 passed (11 files)
verify-migrations.py  126 passed, 0 failed
ruff / mypy strict    clean
```

The existing system is genuinely good at what it does: ingest → validate →
extract → chunk → embed → index → resolve provenance, with forced RLS and
honest status reporting. **It cannot answer a question.** There is no
retrieval query path, no model call, and no conversation storage.

## 2. Why each phase cannot proceed

### Phase 5 — Integration and experience

The acceptance criterion is: *"complete when the entire principal user journey
works end to end without manually manipulating the database."*

The journey as specified breaks at **step 10 of 19**:

| Step | Status |
|---|---|
| 1–3 Visit, understand, sign in | Works |
| 4–6 Workspace and onboarding | Works (no onboarding flow exists) |
| 7–9 Upload, process, inspect source | Works |
| **10–15 Ask, retrieve, answer, verify, inspect evidence** | **Impossible — no such capability** |
| 16–19 Correct memory, revisions, specialist chat, history | **Impossible** |

Workflows B (ingestion) can pass today. Workflows C, D, E, F, G, H in Phase 5C
(critical end-to-end tests) have **no system under test**. Writing an "E2E test"
for retrieval would mean inventing one — which Section 1 of Part III forbids.

Phase 5A.1's own instruction — "identify placeholder features" — resolves to:
the conversation interface is a placeholder, and it says so. Building the
integration cannot precede building the integrated thing.

### Phase 6 — Deployment and operations

Most of Phase 6 is **independent of Phases 3–4** and could be executed now:
deployment architecture, environment separation, secrets policy, health checks,
CI gates, threat model, backup documentation. That portion is genuinely
actionable.

However its acceptance criterion includes a deployment demonstration where
"retrieval works, grounded generation works, evidence verification works,
orchestration works" (6C.6 items 7–11). Those cannot be demonstrated. Phase 6
would therefore produce a real deployment of a system that cannot do the thing
the research claims.

### Phase 7 — Research validation and defense

This is the hard blocker, and it is structural rather than technical.

Phase 7 requires:

- An **objective-to-implementation matrix** where *every* objective has an
  implementation trail. Objectives about evidence-grounded answering,
  claim-level verification and revision-aware memory have **no trail**.
- **Chapter Four results** from genuine implementation and evaluation evidence.
  There are no retrieval results, no verification results, no comparison with a
  conventional RAG baseline — because neither system exists.
- A **comparative chapter** measuring MNEMOS against a RAG baseline across
  correctness, attribution, evidence coverage, conflict detection, abstention
  and latency. **Neither side of this comparison has been built.**
- **Reproducible evaluation infrastructure** (7A.6). None exists.

Producing Chapters Four and Five now would require fabricating results. Part
III, item 1 of the prompt is explicit that this is forbidden, and it is also
academic misconduct. **I will not do it.**

Additionally: the prompt references "the attached official MAAUN guide" and the
approved proposal / Chapters 1–3. **Neither is present in this repository.**
`docs/` contains engineering documentation only. Chapter formatting, citation
style, chapter arrangement and the abstract word limit are all defined by
documents I do not have.

## 3. What is actionable immediately

Ranked by value per unit of risk.

### Option A — Complete Phase 5–7 preconditions (recommended)

Build the missing tiers, then run 5 → 6 → 7 as specified. This is the only
path that ends with a defensible project. Estimated as four sequential
sub-phases, each independently verifiable:

**3A — Hybrid retrieval**
- `match_chunks()` exists and is RLS-safe; needs an application caller.
- Add PostgreSQL full-text search (core FTS — `pg_trgm` is unavailable, verified).
- Reciprocal rank fusion over both result sets.
- Workspace, version and information-status filters.
- Endpoint: `POST /knowledge/workspaces/{id}/search`.
- Tests: ranking, filter correctness, RLS (non-member gets nothing),
  determinism, empty result.

**3B — Grounded generation with citations**
- OpenRouter adapter: timeouts, bounded retries, usage capture, model ID per
  execution, capability check. *(Adapter does not exist yet — this is new code,
  not a wrapper.)*
- Prompt construction separating trusted instructions from retrieved text.
- Answer + per-claim citation mapping to `chunk_id` → provenance.
- Refusal path when retrieval is empty (FR-010).
- Schema: `conversations`, `messages`, `answers`, `claims`, `execution_records`.
- Tests: citation integrity, abstention, provider failure, injection resistance.

**3C — Claim verification and revision-aware memory**
- Verifier: each claim vs. its cited passages, with a verdict.
- Corrections: user-initiated, approval-gated, revision + supersession records.
- Conflict detection between sources on the same claim.
- Tests: superseded-not-current, conflict surfacing, unauthorized write rejected.

**3D — Agents and orchestration**
- Four real roles over the services above (not four LLM personas).
- Orchestrator delegates, merges, verifies; specialist direct mode.
- Execution traces persisted from real events.
- Tests: delegation, trace integrity, authorization per agent.

**4A — Evaluation**
- Labelled dataset, RAG baseline, identical models/embeddings/parameters.
- Metrics: correctness, attribution, evidence coverage, conflict detection,
  abstention + false abstention, latency, cost.
- Reproducible runner with recorded config.

This is substantial — realistically many sessions of work — but it is the only
route to a project that survives examination.

### Option B — Honest scoped deliverable

Accept the current boundary and re-scope the research to what is built: a
provenance-aware ingestion and indexing system. This would require **supervisor
approval to change the approved title and objectives**, which the prompt
forbids doing silently.

### Option C — Phase 6 operational work only

Deploy and harden what exists: hosting config, CI gates, threat model, backup
and monitoring documentation, secrets audit. Real, useful, and honest — but it
does not produce a defense-ready research project, and Phase 6C.6's acceptance
list still cannot be satisfied.

## 4. What I built this session instead

Rather than fabricate work, I produced verified audit artefacts:

1. `docs/TRACEABILITY_MATRIX.md` — every requirement mapped to code, tests and
   an honest status. This is directly reusable as Phase 7A.2's deliverable.
2. This report — the precondition evidence and unblocking options.
3. `docs/RELEASE_STATUS.md` — an accurate release-candidate record of what
   exists (Phase 5C.5's deliverable, honestly scoped).

Each is committed separately and is immediately useful for a supervisor
conversation.

## 5. What I need to continue

Three things, none of which I can decide alone:

1. **Authorization to build Phases 3–4** (Option A). This is a material scope
   increase over the prompt's assumption that they already exist. It is the
   decision that unblocks everything else.
2. **The MAAUN guide and approved Chapters 1–3.** Phase 7B cannot be produced
   against a formatting standard I have not seen, and Chapter Four must align
   with the approved objectives.
3. **Confirmation of the approved chapter arrangement** (five-chapter vs. the
   permitted six-chapter variant) — the prompt acknowledges both exist and says
   to follow the supervisor-approved structure.

If Option A is approved I will execute 3A → 3B → 3C → 3D → 4A in order, each
with its own verification gate and commit, and only then begin Phase 5.
