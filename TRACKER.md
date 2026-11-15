# MNEMOS — Project Tracker

Authoritative phase status. A task is complete only when its acceptance
criteria have been verified. Never mark work complete on the basis of
intent.

## Current phase

**Phase 2 — Knowledge Infrastructure and Ingestion.** Branch
`arena/548c24a5-mnemos` (Phase 1 merged to `main` as `2f18c77`).

## Status by subphase

| Subphase | Implementation | Verification | Committed |
|---|---|---|---|
| 1A — Application infrastructure & backend foundation | Complete | Complete (27 backend + 23 frontend tests at 1A) | Yes |
| 1B — Supabase integration & database architecture | Complete | Complete locally (62 schema/RLS checks, 72 backend tests) | Yes |
| 1C — Application shell & responsive experience | Complete | Complete (78 frontend tests incl. axe audits + 28 contrast checks) | Yes |
| 2A — Provenance-aware schema | Complete | Complete locally (109 schema/RLS checks, 95 backend tests) | Yes |
| 2B — Controlled document ingestion | Not started | — | No |
| 2C — Chunking, embeddings and vector indexing | Not started | — | No |

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
| `pytest` | **95 passed** |
| `scripts/verify-migrations.py` | **109 passed, 0 failed** (real PostgreSQL 16) |
| `npm run typecheck` | Passed |
| `npm test -- --run` | **78 passed** (9 files) |
| axe-core accessibility audit | 7 surfaces, 0 violations |
| WCAG contrast assertions | 28 passed (both themes) |
| `npm run build` | Passed — 447 kB JS / 44 kB CSS |
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
  including HNSW). `pg_trgm` is **not**, so lexical search must use core
  full-text search. Supabase availability still to be confirmed remotely.
- ADR-0006 (pgvector) remains `Proposed` — validated locally, not remotely.
- ADR-0007/0008/0009 accepted in Phase 1 (API conventions, access layering,
  styling).
- OpenRouter model IDs still unselected; no calls made.

## Next recommended task

**Phase 2B — controlled document ingestion**: upload/note endpoints, private
storage writes, text extraction for plain text/Markdown/PDF, status machine,
and the submission UI. Then 2C (deterministic chunking + embeddings).

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
