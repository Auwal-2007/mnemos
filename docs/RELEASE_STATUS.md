# MNEMOS — Release Status

**Version:** 0.1.0
**Commit:** `38da949` (audited) + audit artefacts
**Date:** 2026-11-15
**Classification:** Engineering prototype — ingestion and provenance tier.
**NOT a release candidate** for the research project as specified.

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

## 2. What does not exist

| Capability | State |
|---|---|
| Ask a question about the corpus | **Absent** — no retrieval query path |
| Generated answers | **Absent** — no model adapter exists |
| Citations from an answer | **Absent** — no answer to cite |
| Claim-level verification | **Absent** |
| Corrections, revisions, supersession | **Absent** — columns exist, unused |
| Conflict detection | **Absent** |
| Any agent execution | **Absent** — four roles are documented contracts only |
| Conversation persistence | **Absent** — no table |
| Evaluation infrastructure | **Absent** |

The conversation interfaces render, state plainly that sending is disabled, and
explain why. That is the correct behaviour given nothing is behind them.

## 3. Verified this session

Re-established from a clean environment, not carried over from a report:

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest -q` | **247 passed** (with `pgserver`; 5 integration tests skip without it) |
| Frontend tests | `vitest run` | **119 passed** (11 files) |
| Migrations + RLS | `scripts/verify-migrations.py` | **126 passed, 0 failed** against real PostgreSQL 16 + pgvector 0.6.2 |
| Backend lint | `ruff check app tests` | clean |
| Backend types | `mypy app` (strict) | clean, 44 files |
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
  and wire formats are configured, not observed.
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
| **P1** | The product cannot answer questions; the research objective is unmet | Project-defining |
| **P1** | Phases 3 and 4 absent | Blocks Phase 5–7 as specified |
| **P2** | No live-environment verification of anything | Deployment risk |
| **P2** | Re-index invalidates existing evidence references | Documented in `CHUNKING_AND_INDEXING.md §7`; Phase 3C must treat an unresolvable reference as unsupported |
| **P3** | Chunking is character-based | Long unpunctuated text lands near the 4000-char maximum |
| **P3** | Instrument Serif is Latin-only | Display fallback in other scripts |
| **P3** | HNSW parameters untuned | `m=16, ef_construction=64` are reasoned, not measured |

## 7. Verdict

This is a **credible engineering foundation** with unusually good provenance
discipline, security posture and test coverage for its tier. It is **not** the
system the research title describes, and it must not be presented as one.

Release-candidate status requires Phases 3 and 4 to exist. See
`docs/phases/phase-5-7-blocked-report.md`.
