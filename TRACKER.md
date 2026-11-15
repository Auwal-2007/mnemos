# MNEMOS — Project Tracker

Authoritative phase status. A task is complete only when its acceptance
criteria have been verified. Never mark work complete on the basis of
intent.

## Current phase

**Blocked pending scope decision.** Phase 2C and the UI redesign are complete
and merged. A precondition audit of Phases 5–7 established that **Phases 3
(retrieval, generation) and 4 (verification, memory, agents, evaluation) do not
exist** in this repository. Phases 5–7 cannot be executed against a system that
cannot retrieve or answer. Evidence and unblocking options:
`docs/phases/phase-5-7-blocked-report.md`.

Branch `arena/1ee787c5-mnemos` (base `38da949`).

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
| 3 — Retrieval, grounded generation | **Not implemented** | — | No |
| 4 — Verification, memory, agents, evaluation | **Not implemented** | — | No |
| 5 — Product integration | **Blocked** | Journey breaks at step 10 of 19 (cannot ask a question) | No |
| 6 — Deployment & operations | **Blocked** (deployment demonstration needs retrieval) | — | No |
| 7 — Research validation & defense | **Blocked** (no Chapter Four evidence exists) | — | No |

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
| `mypy app` (strict) | Passed — 30 source files |
| `pytest` | **247 passed** (with `pgserver`); **242 passed, 5 skipped** without it — the 5 are the real-PostgreSQL integration tests |
| `scripts/verify-migrations.py` | **126 passed, 0 failed** (real PostgreSQL 16, pgvector 0.6.2) |
| `npm run typecheck` | Passed |
| `npm test -- --run` | **119 passed** (11 files) |
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
