# MNEMOS — Completion Audit

**Date:** 2026-11-16
**Branch:** `arena/1ee787c5-mnemos` (base `38da949`)
**Method:** direct inspection of the working tree, plus executed test runs. No
prior completion claim was trusted.

This is the Stage 0 reconciliation required before any further implementation.

---

## 1. Environment capability, established by test

This governs what can honestly be called *verified*.

| Capability | Status | Evidence |
|---|---|---|
| GitHub, npm, PyPI egress | **Available** | HTTP 200 |
| `api.openrouter.ai` | **Network-blocked** | connection fails, code 000 |
| `*.supabase.co` | **Network-blocked** | connection fails, code 000 |
| Live Supabase project | **Absent** | no `.env`, no URL configured |
| OpenRouter API key | **Absent** | no `.env`, no key in env |
| PostgreSQL 16 + pgvector 0.6.2 | **Available locally** | embedded `pgserver` |
| Browser / Playwright Chromium | **Unavailable** | download blocked |

**Consequence, stated once and applied throughout:** every provider-dependent
and deployment-dependent requirement in this document is **BLOCKED**, not
"in progress". It cannot be completed in this environment by any amount of
engineering. All provider-*independent* work is completed and run.

Nothing in this repository has ever been validated against a live model, a live
embedding endpoint, or a hosted Supabase instance. That is a fact about the
environment, not a shortfall of the code — but it means no quality claim may be
made from live evidence, because none exists.

---

## 2. Executed baseline

Re-run against the current working tree, from a clean virtualenv:

```
backend pytest          442 passed
verify-migrations.py    221 passed, 0 failed
ruff check / format     clean (92 files)
mypy app (strict)       clean (63 files)
```

Frontend: `node_modules` is not present and cannot be assumed; `npm ci` is
required before its suite can run. The last recorded result is 119 tests over
11 files, which is a **prior** result, not a current one, and is labelled as such
in `PHASE_STATUS.md`.

---

## 3. What exists, by layer

### 3.1 Backend (63 source files, 47 routes)

| Area | State |
|---|---|
| Config, errors, middleware, health | Implemented, tested |
| Auth (Supabase JWT) | Implemented, tested |
| Workspaces / membership / preferences | Implemented, tested |
| Ingestion (upload, note, validation, extraction, storage) | Implemented, tested |
| Chunking + embeddings + indexing | Implemented, tested |
| Hybrid retrieval (RRF, k=60) | Implemented, tested |
| Grounded generation + citation binding | Implemented, tested against fake provider |
| Verification (lexical + model methods) | Implemented, tested |
| Corrections / supersession / conflicts | Implemented, tested incl. real PostgreSQL |
| Agents (4 roles) + orchestration traces | Implemented, tested |

### 3.2 Frontend (96 files)

| Area | State |
|---|---|
| Shell, routing, navigation, themes | Implemented |
| Landing page | Implemented (decorative; no product claims proven) |
| Auth (Supabase) | Implemented |
| Workspace list | Implemented |
| Knowledge / sources | Implemented, wired to real API |
| API client (centralized, typed errors) | Implemented, tested |
| **Conversations** | **Shell only — no client, composer disabled** |
| **Retrieval** | **Not wired** |
| **Memory / corrections / conflicts** | **Not wired** |
| **Agents / orchestration traces** | **Not wired** |
| **EvidencePanel** | **Exported, consumed nowhere** |

### 3.3 Evaluation

**Absent.** No dataset, no metrics, no baseline, no runner, no results.

---

## 4. Defects previously found and fixed (Phases 3B–3D)

Recorded because they were latent in code that passed its tests:

1. Transport failures escaped the completion provider as raw `httpx` exceptions;
   `CompletionError` handlers missed them and the API returned 500.
2. Exhausted retries discarded the cause (429 vs 5xx indistinguishable).
3. An answer with no verification available reported as **undegraded**.
4. `apply_knowledge_correction` relied on `auth.uid()` inside `SECURITY DEFINER`.
5. `current_provenance` view had no grant of its own (users got permission denied).

Each now has a regression test.

---

## 5. What the user's completion mandate requires, mapped to reality

| Requirement | Achievable here? | Basis |
|---|---|---|
| Full frontend integration | **Yes** | code only |
| Evaluation harness + metrics | **Yes** | local Postgres |
| Real retrieval measurements (lexical) | **Yes** | real FTS |
| Real retrieval measurements (semantic) | **No** | needs embeddings provider |
| Answer-quality metrics | **No** | needs a model |
| RAG baseline comparison | **Partial** | baseline *architecture* + harness yes; model-dependent numbers no |
| Live Supabase verification | **No** | network blocked |
| Live OpenRouter verification | **No** | network blocked |
| Deployment + production verification | **No** | no host, no credentials |
| Browser E2E (Playwright) | **No** | Chromium download blocked |
| Security hardening (code-level) | **Yes** | code + local DB |
| Performance measurement (backend) | **Partial** | local Postgres only |

This table is the honest boundary of the session. It is repeated in
`PHASE_STATUS.md` so it cannot be mistaken for a footnote.
