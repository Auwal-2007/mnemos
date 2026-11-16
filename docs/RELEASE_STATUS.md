# MNEMOS — Release Status

**Version:** 0.2.0-dev
**Commit:** `7a8a6ba` (Phases 3A–3D complete) + this documentation pass
**Date:** 2026-11-15
**Classification:** Engineering prototype — retrieval, generation, verification
and agent tier, verified **locally only**.
**NOT a release candidate** for the research project as specified, and not
deployable without credentials.

This is the honest record required by Phase 5C.5. It states what exists, what
does not, and what is unverified. It does not label the product production-ready.

---

## 1. What works end to end

A user can sign up, sign in, land in a private workspace, upload a PDF / text /
Markdown file or write a note, watch real processing status advance, and inspect
the resulting source: its versions, its extracted text, its chunks with exact
character ranges, its page numbers, its embedding state, and the provenance
record resolving any chunk back to a specific version of a specific document.

Every number shown comes from the API. Nothing is seeded, sampled or simulated.

A user can ask a question about their corpus and receive a grounded answer whose
every claim carries a citation resolvable to a specific passage, with an explicit
abstention when no evidence exists. Each answer can be verified claim-by-claim,
its claims' verdicts inspected, a correction proposed, reviewed and applied as a
revision that preserves the original, and conflicting passages detected. The
orchestrated path runs four agents and records what each did.

**All of that is exercised through tests and the API only.** No live model or
embedding call has ever been made, and the frontend does not yet consume the new
endpoints.

## 2. What does not exist

| Capability | State |
|---|---|
| Frontend for asking questions | **Absent** — composers remain disabled; `EvidencePanel` unwired |
| Direct specialist chat (FR-002) | **Partial** — role exists in schema; no endpoint or UI |
| Live-environment operation | **Absent** — no Supabase project, no API key, never called |
| Evaluation: retrieval quality, faithfulness, baselines | **Absent** — Phase 4A |
| Agent collaboration beyond the fixed plan | **Absent** by design (ADR-0013) |
| Load, concurrency, penetration testing | **Absent** |
| Deployment | **Absent** |

The conversation interfaces render, state plainly that sending is disabled, and
explain why. That remains correct until the frontend is wired to the answer
endpoints, because a working backend is not a working product.

## 3. Verified this session

Re-established from a clean environment, not carried over from a report:

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest -q` | **442 passed** (with `pgserver`; integration tests skip without it) |
| Frontend tests | `vitest run` | **119 passed** (11 files) — unchanged since the redesign |
| Migrations + RLS | `scripts/verify-migrations.py` | **221 passed, 0 failed** against real PostgreSQL 16 + pgvector 0.6.2 |
| Backend lint | `ruff check app tests` | clean |
| Backend types | `mypy app` (strict) | clean, 63 files |
| Frontend types | `tsc --noEmit` | clean |
| Frontend build | `npm run build` | succeeds |
| Accessibility | axe-core | 0 violations across 10 surfaces |
| Contrast | token-derived WCAG ratios | 28 assertions pass |
| Secrets | `verify.sh` gate | no `.env`, no JWTs, no service-role key in frontend |

## 4. Not verified, and not claimed

- **No browser rendering.** No browser is available in this environment
  (Playwright's Chromium download is blocked). Layout, motion and the 3D scene
  were reasoned and structurally tested, never seen. The WebGL scene has never
  executed.
- **No live Supabase project.** Migrations are proven against a local
  PostgreSQL 16 with pgvector 0.6.2. Whether the target Supabase project has
  pgvector enabled is **unconfirmed**; the migration raises
  `feature_not_supported` rather than failing silently.
- **No live embedding or model call.** No credentials exist here. Dimensions
  and wire formats are configured, not observed. Provider behaviour is tested
  through `httpx.MockTransport`, which proves request shape, error mapping and
  usage parsing — **not** that a real model answers well, or answers at all.
- **No quality measurement of any kind.** Retrieval recall/precision, answer
  faithfulness and abstention correctness are unmeasured. The verification
  thresholds (0.70 / 0.45) are judgement calls, not calibrated constants. Phase
  4A exists to replace both with evidence.
- **No real-device testing** for touch targets, safe-area insets or mobile
  Safari viewport units.
- **No load, concurrency or penetration testing.**

## 5. Environment and configuration

Required variables are documented in `.env.example`. The deployment shape is a
static frontend, a Python ASGI backend, Supabase for Postgres/Auth/Storage, and
an external embeddings provider. Model identifiers are settings, never code.
No service-role key is referenced anywhere in the frontend.

## 6. Known limitations by severity

| Sev | Issue | Impact |
|---|---|---|
| **P0** | None identified | — |
| **P1** | No quality measurement; the research claim is unevidenced | Project-defining — Phase 4A |
| **P1** | The frontend cannot ask a question yet | The product is not usable end to end by a person |
| **P1** | Nothing has ever run against a live provider or Supabase project | Every integration is unproven in situ |
| **P2** | No live-environment verification of anything | Deployment risk |
| **P2** | Re-index invalidates existing evidence references | Documented in `CHUNKING_AND_INDEXING.md §7`. Phase 3C treats an unresolvable citation as `unverified` — which is what it is, not a support failure |
| **P3** | Chunking is character-based | Long unpunctuated text lands near the 4000-char maximum |
| **P3** | Instrument Serif is Latin-only | Display fallback in other scripts |
| **P3** | HNSW parameters untuned | `m=16, ef_construction=64` are reasoned, not measured |

## 7. Verdict

This is now a **working retrieval-and-grounding system** with the full path from
question to cited, verifiable answer implemented and covered by 442 tests, and
with provenance and separation-of-duties discipline carried through the agent
layer. The honesty properties the design turns on — abstention over guessing,
`unverified` distinct from `unsupported`, corrections that never overwrite,
skipped checks reported as skipped — are defended by tests rather than asserted
in prose.

What it is **not**:

- a *demonstrated* system — nothing has run against a real model or a real
  Supabase project;
- a *measured* system — no retrieval or faithfulness number exists;
- a *usable* system — a person cannot yet ask a question in the UI.

Release-candidate status requires Phase 4A's measurements, a live-environment
run, and the frontend wiring. See
`docs/phases/phase-5-7-blocked-report.md`.
