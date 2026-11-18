# MNEMOS — Project Tracker

Authoritative phase status. A task is complete only when its acceptance
criteria have been verified. Never mark work complete on the basis of
intent.

## Current phase

**Session complete for everything achievable here.** Phase 4A built and measured;
Phase 5A frontend integration done; Phase 6A security hardening and the operations
documentation set written; Phase 7 handover documents produced.

**Blocked, not outstanding:** live provider verification, hosted-database
verification, deployment and browser E2E all require network egress or a host that
this sandbox does not have. See `FINAL_SOFTWARE_COMPLETION_REPORT.md` §10 for the
exact action each one needs.

The scope decision that blocked Phases 5–7 has been taken: the user authorised
**Full Option A** — 3A hybrid retrieval → 3B grounded generation → 3C
verification and memory → 3D agents → 4A evaluation. Phases 3A–3D are now built
and verified locally.

**Phase 7 remains deferred** by user choice: build code and operations first,
thesis chapters later. Chapter arrangement will follow the MAAUN guide once it
is supplied; no chapter count is assumed.

Branch `arena/1ee787c5-mnemos` (base `38da949`).

## Post-release defect fix — authentication (branch `arena/aaa29d47-mnemos`)

Two symptoms were reported after the first release: "even though I filled all API
keys it still doesn't allow messages", and "when I login it still says workspace
session not working". They are one defect.

| Item | Status | Evidence |
|---|---|---|
| Root cause: `verify_token` accepted only HS256 against `SUPABASE_JWT_SECRET`, so asymmetric-key projects rejected every valid token | FIXED | `backend/app/infrastructure/auth.py` |
| Auth API fallback (`GET /auth/v1/user`, 60 s success cache, expiry rejected locally) | TESTED | `backend/tests/unit/test_auth.py` — 21 tests |
| Server faults return 503, never 401, so a signed-in user is not told to sign in | TESTED | `test_auth.py`, `tests/api/test_authorization.py` |
| Connection state tells the real reason (signed out / unconfigured / server error / no workspace) | TESTED | `connectionState.test.ts` — 8 tests |
| Create-workspace panel for a signed-in user with zero workspaces | TESTED | `CreateWorkspacePanel.test.tsx` — 3 tests |
| Verified against a real Supabase project | NOT DONE — BLOCKED | no network egress to `*.supabase.co` (K-01) |

Full suites after the fix: backend **497 passed**, migration/RLS verifier
**223 passed / 0 failed**, `mypy` 74 files clean, frontend **153 passed**,
`tsc --noEmit` clean, production build succeeds.

## Status by subphase

| Subphase | Implementation | Verification | Committed |
|---|---|---|---|
| 1A — Application infrastructure & backend foundation | Complete | Complete (27 backend + 23 frontend tests at 1A) | Yes |
| 1B — Supabase integration & database architecture | Complete | Complete locally (62 schema/RLS checks, 72 backend tests) | Yes |
| 1C — Application shell & responsive experience | Complete | Complete (78 frontend tests incl. axe audits + 28 contrast checks) | Yes |
| 2A — Provenance-aware schema | Complete | Complete locally (109 schema/RLS checks, 95 backend tests) | Yes |
| 2B — Controlled document ingestion | Complete | Complete locally (175 backend tests, 87 frontend tests) | Yes |
| 2C — Chunking, embeddings and vector indexing | Complete | Complete locally (242 backend tests incl. 12 real-PostgreSQL; 126 migration checks; ADR-0010) | Yes (merged) |
| UI redesign | Complete | 119 frontend tests, 10 axe audits 0 violations, build verified | Yes (merged) |
| 3A — Hybrid retrieval (lexical + semantic, fused) | Complete | Complete locally — 21 service + 14 API tests | Yes, in the working tree before `7a8a6ba` |
| 3B — Grounded generation with citation binding | Complete | Complete locally — 24 unit + 20 API tests | Yes, in the working tree before `7a8a6ba` |
| 3C — Verification, corrections, conflict detection | Complete | Complete locally — 38 unit + 4 real-PostgreSQL tests | Yes, in the working tree before `7a8a6ba` |
| 3D — Agents and orchestration | Complete | Complete locally — 29 orchestration + 14 provider tests; **221** migration checks; **442** backend tests total | Yes (`7a8a6ba`) |
| 4A — Evaluation and reproducibility | **Next** | — | No |
| 4B — Agent collaboration expansion | Not started | — | No |
| 5 — Product integration | Ready to start (journey can now reach step 10 and beyond) | — | No |
| 6 — Deployment & operations | Not started. Requires credentials for a live demonstration | — | No |
| 7 — Research validation & defense | **Deferred by user choice** | Waits on MAAUN chapter guide | No |

### What "complete locally" does and does not mean

Every phase above is verified **in this environment only**: real PostgreSQL via
an embedded server, migrations applied from scratch, and the API driven through
its own test client. There is **no live Supabase project**, so RLS is proven
against a faithful local reconstruction of Supabase's roles and auth functions,
not against the hosted service. There has been **no live embedding call and no
live model call**, ever, in this repository's history. Retrieval and answer
quality are therefore unmeasured — that is exactly what 4A exists to do, and no
quality claim is made before it.

Legend for the "Verification" column: **local** means executed in this
environment; **remote** means against a live Supabase project.

## Completed work

### Phase 0 (merged)
- Repository inspected; stack selected and documented (ADR-0001–0006).
- Engineering control documents, environment templates, CI, pre-commit.
- Supabase/OpenRouter strategy documented; no schema or model calls.

### Phase 1A
- [x] Backend layered foundation: app factory, lifespan, `/api/v1` routing,
      typed config with placeholder detection, canonical error envelopes,
      request-id middleware, services/schemas separation, health + readiness.

### Phase 1B
- [x] Three idempotent migrations: schema, RLS policies, private storage bucket.
- [x] Four foundational tables (`profiles`, `workspaces`,
      `workspace_members`, `user_preferences`) with FKs, checks, indexes,
      timestamps and triggers.
- [x] Signup bootstrap trigger (profile + preferences + default workspace +
      owner membership).
- [x] RLS enabled and forced on every table; deny-by-default; no `anon` grants.
- [x] JWT verification (HS256, `sub`+`exp` required, `alg:none` rejected).
- [x] Repository interfaces + Supabase implementations; no arbitrary SQL path.
- [x] Authenticated API: `/me`, `/me/preferences`, `/workspaces` CRUD, members.

### Phase 1C
- [x] Application shell: collapsible desktop sidebar, mobile drawer + bottom
      navigation, page header/container, user menu with sign-out.
- [x] Design system: tokens for colour (light/dark), type, spacing, radius,
      borders, shadows, motion, breakpoints.
- [x] Home dashboard with real system status and real workspace data.
- [x] Conversation components for both modes (orchestrated and direct
      specialist), honest empty states, disabled composer with reason.
- [x] Agent directory with all four planned roles and their contracts.
- [x] Knowledge workspace structure, settings (working theme switch),
      sign-in page, planned-area placeholder, 404.

### Phase 2C
- [x] Deterministic chunking (`paragraph-window`, target 900 / overlap 150 /
      hard max 4000) with measured justification and a pinned-config test.
- [x] Chunk configuration recorded per chunk; the indexer refuses to mix chunk
      shapes in one version.
- [x] Embedding adapter isolated from the chat provider: embeddings endpoint
      only (chat paths refused), configurable model/dimension/batch, bounded
      retries on 429/5xx/timeouts, per-vector dimension validation, usage
      capture. ADR-0010.
- [x] `chunk_embeddings` with `vector(N)` from configuration, HNSW cosine
      index, RLS enabled+forced, `match_chunks()` `SECURITY INVOKER`.
- [x] `IndexingService`: resume-on-retry, no duplicate chunks or vectors,
      `ready` only on full success, explicit re-index.
- [x] Endpoints: `POST /knowledge/sources/{id}/index` and `/reindex`.
- [x] Frontend: index/rebuild controls, chunk list with exact character ranges
      and page numbers, honest "not searchable yet" copy.
- [x] Docs: `docs/CHUNKING_AND_INDEXING.md`, ADR-0010.

### Phase 2B
- [x] `IngestionPipeline` — ordered, failure-aware ingestion with a defined
      end state for every failure point (docs/INGESTION_PIPELINE.md).
- [x] Validation: size, declared type, **content-detected** type, encoding,
      binary sniffing, filename normalization, server-chosen storage paths.
- [x] Extraction registry: plain text, Markdown (with heading offsets), PDF
      (page-preserving via pypdf). Explicit codes for `no_text_layer`,
      `encrypted_pdf`, `corrupt_pdf`, `unsupported_encoding`, `too_much_text`.
- [x] Notes ingested as versioned sources through the same pipeline.
- [x] Idempotency keys prevent duplicate sources on retry.
- [x] New versions retire the old one and keep its bytes, text and chunks.
- [x] Deletion removes storage objects first, then cascades the database.
- [x] Endpoints: upload, note, new version (file/note), download URL, delete.
- [x] Frontend: real submission panel (upload + note tabs), source list with
      real statuses, detail panel with version history and deletion, status
      legend. `/sources` now loads the workspace instead of a placeholder.
- [x] Docs: `docs/INGESTION_PIPELINE.md`.

### Phase 2A
- [x] Two migrations: `20260102000000_knowledge_schema.sql` and
      `20260102000100_knowledge_rls.sql`.
- [x] Six tables with composite same-workspace FKs, partial unique indexes
      (one current version per source), and CHECK constraints on hashes,
      offsets and length agreement.
- [x] Three integrity triggers: version immutability, chunk/source agreement,
      provenance/chunk agreement.
- [x] `resolve_chunk_provenance(uuid)` — `SECURITY INVOKER` resolution of the
      full provenance contract.
- [x] RLS enabled and forced on all six tables; users may read but never
      write derived data (chunks, provenance).
- [x] Domain models (`app/domain/knowledge.py`) incl. `ProvenanceReference`,
      `SourceLocation`, `ChunkDraft`; repository protocols and Supabase
      implementations; `KnowledgeService`; six read/delete endpoints.
- [x] Documentation: `DATABASE_SCHEMA.md`, `PROVENANCE_MODEL.md`,
      `DATA_DICTIONARY.md` with Mermaid ER diagrams.

## Tests and verification status

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | Passed |
| `mypy app` (strict) | Passed — 74 source files |
| `pytest` | **487 passed** (with `pgserver`) |
| `scripts/verify-migrations.py` | **223 passed, 0 failed** (real PostgreSQL 16, pgvector 0.6.2) |
| `npm run typecheck` | Passed |
| `npm test -- --run` | **142 passed** (13 files) |
| axe-core accessibility audit | 10 surfaces, 0 violations |
| WCAG contrast assertions | 28 passed (both themes) |
| `npm run build` | Passed — entry 151 kB, vendor 392 kB, motion 130 kB, `three` 472 kB (lazy) / 140 kB CSS |
| `./scripts/verify.sh` (full) | All checks passed |
| Live backend: health/ready/docs/openapi | 200 |
| Live backend: protected routes without token | 401 with envelope |
| Frontend dev proxy → backend | Verified |
| `.env` not tracked | Verified |

### Not executed (tooling/credentials)

- **Pixel-level visual verification** at 1440/1024/768/390/360. No browser
  could be installed in this environment (Playwright Chromium download and
  dependency install both failed). Layout decisions, breakpoints, landmarks
  and colour contrast are verified programmatically instead; see
  `docs/phases/phase-1c-report.md`.


- Applying migrations to a live Supabase project.
- End-to-end signup → JWT → protected request against Supabase Auth.
- RLS behaviour through PostgREST (verified only via direct PostgreSQL).
- Storage upload/download through the Storage API.
- OpenRouter connectivity (out of scope for Phase 1).

### Known open item

- Add Playwright visual regression snapshots at the five required widths once
  a browser is available.

## Blockers

- Remote Supabase verification requires a project and credentials
  (see "Outstanding manual setup").
- **Live OpenRouter and Supabase hosts are unreachable from this sandbox** —
  measured, not assumed: `api.openrouter.ai`, `openrouter.ai` and `db.supabase.co`
  all fail to connect, while `github.com`, `registry.npmjs.org` and `pypi.org`
  respond. Live provider verification therefore cannot be performed here even
  with credentials, and is reported BLOCKED rather than attempted.

## Phase 4A — evaluation (this session)

| Item | Status |
|---|---|
| Dataset schema with mandatory ground-truth basis + versioning | VERIFIED |
| 8-document corpus, 22 cases across 9 behavioural categories | VERIFIED |
| Calibration/evaluation split so thresholds are not fitted on reported data | VERIFIED |
| Metrics: Recall@K, Precision@K, MRR, nDCG, citation precision/recall, abstention | VERIFIED (unit-tested) |
| Real-PostgreSQL harness: all migrations + real chunker + real retrieval function | VERIFIED |
| Fair RAG baseline sharing corpus, k and query parsing | VERIFIED |
| Reproducible CLI + per-run artefacts (results, dataset, report) | VERIFIED |
| Generated evaluation report | VERIFIED (`docs/EVALUATION.md`, `eval-results/final/report.md`) |
| Evidence-sufficiency floor calibrated on held-out split | VERIFIED — 0.25, acc 0.750 held-out |
| Answer correctness / faithfulness / cost | BLOCKED — no model provider |
| Semantic and hybrid retrieval measurement | BLOCKED — no embedding provider |

### Defect found and fixed by the evaluation

`websearch_to_tsquery` joins every term with AND, so natural-language questions
matched almost nothing: **73.7% of answerable cases returned no evidence.**
Fixed in `20260104000000_retrieval_query_relaxation.sql` (strict first, OR
fallback). Recall@5 0.211 → 0.605, MRR 0.263 → 0.789 on the corpus as it stood.

## Technical decisions

- pgvector **is available** in the local PostgreSQL 16.2 harness (0.6.2,
  including HNSW; a `vector(N)` column rejects other lengths). `pg_trgm` is
  **not**, so lexical search must use core full-text search. Supabase
  availability still to be confirmed remotely.
- Embeddings use a **separate provider concern** from chat (ADR-0010). No real
  embedding request has been made; the dimension is configured, not assumed.
- ADR-0006 (pgvector) remains `Proposed` — validated locally, not remotely.
- ADR-0007/0008/0009 accepted in Phase 1 (API conventions, access layering,
  styling).
- OpenRouter model IDs still unselected; no calls made.

### UI redesign (cross-cutting, after 2C)
- [x] Original visual identity: warm charcoal ramp, three semantic hues
      (teal = live intelligence, brass = the human record, rose = conflict),
      Instrument Serif display / Inter UI / JetBrains Mono for literal values.
      Contrast computed from the token file in both themes.
- [x] Public landing page at `/`; product moved to `/app`. Hero 3D scene
      (raw Three.js, lazy-loaded, designed SVG fallback, reduced-motion static
      frame) plus a pipeline walkthrough with per-step Implemented/Planned
      labels, an interactive agent topology and a provenance showcase.
- [x] Product shell: grouped nav, collapsible rail, page transitions, ⌘K
      command palette validated as a combobox/listbox.
- [x] Redesigned dashboard, knowledge workspace, agent directory, conversation
      modes, evidence drawer, settings, sign-in.
- [x] Motion system with a single reduced-motion policy point; cursor
      spotlight/tilt/magnetic primitives that write custom properties only.
- [x] ADR-0011, `docs/DESIGN_SYSTEM.md`, `docs/phases/ui-redesign-report.md`.
- [ ] **Not verified:** no browser was available, so nothing was seen
      rendered and WebGL never executed. See the report's honest gaps.

## Next task — requires authorization

**Phase 3A — hybrid retrieval**, then 3B (grounded generation), 3C (verification
and revision-aware memory), 3D (agents), 4A (evaluation), and only then Phase 5.

`match_chunks()` already exists and is RLS-safe but has **no application
caller**. Core PostgreSQL FTS is required because `pg_trgm` is unavailable
(verified). Fusion should be reciprocal rank. The evidence drawer built during
the redesign is the intended destination for a citation click once answers
exist.

Building Phases 3–4 is a material scope increase beyond the assumption in the
Phases 5–7 brief. It requires explicit approval.

## Audit artefacts (this session)

- `docs/TRACEABILITY_MATRIX.md` — every requirement to code/test/status.
- `docs/phases/phase-5-7-blocked-report.md` — precondition evidence.
- `docs/RELEASE_STATUS.md` — honest release-candidate record.

## Outstanding manual setup (user)

1. Create a Supabase project; copy `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY` into `.env`.
2. Apply migrations: `npx supabase link --project-ref <ref>` then
   `npx supabase db push` (review the SQL first — it is additive only).
3. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` for the frontend
   (anon key only).
4. Create an account through the app; the signup trigger provisions the
   profile, preferences and default workspace.
5. Optionally set OpenRouter credentials for the later AI phase.
