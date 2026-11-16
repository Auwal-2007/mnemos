# MNEMOS — Changelog

All notable changes are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
pre-release (`0.x.y`) until the first feature release.

## [Unreleased]

## [0.3.0-dev] — 2026-11-16
### Added — Phase 5A frontend integration (conversations, retrieval, memory, agents)

- Typed API clients for conversations, messages, grounded answers, verification,
  retrieval, memory (corrections and conflicts) and agents/orchestration. Types
  mirror the generated OpenAPI schemas, so a server-side rename is a type error
  rather than a silently ignored field.
- `useConversations`, `useConversationMessages`, `useMemory` hooks following the
  existing `useSources` conventions: explicit loading/error state, no sample
  data, optimistic question insertion removed again on failure.
- `AnswerView` renders a grounded answer in all three states it can actually be
  in — answered, abstained, degraded — with per-claim citations that open the
  real provenance record, and superseded citations visibly marked.
- Orchestrator and direct-specialist conversation pages connected to the live
  endpoints. Both previously disabled their composer and stated that no model
  execution existed; that is no longer true, so the copy and behaviour changed.
- Memory workspace at `/app/memory`: correction proposals, review, apply-as-
  revision, conflict detection and resolution, with the revision link shown so
  the original record is visibly still present.
- `EvidencePanel` is now consumed, wired to citation clicks.
- `ConversationView` gained `afterTranscript` and `sending` props so the answer
  renders after the question it answers.

### Fixed — stale capability claims removed from the interface

The interface told users that agents were "not connected to a model", that
"no model execution or orchestration exists yet", and that specialists were
"planned". All three became false in Phases 3B–3D and were still on screen.
Corrected in the conversation pages, the conversations index, the navigation
notes, the agent catalogue, the dashboard and the landing page. Tests now assert
the truthful copy and fail if the old text returns.

### Tests

- Frontend 119 → 142 (13 API contract tests, 9 AnswerView tests, rewritten
  conversation-mode tests asserting real behaviour instead of the old
  not-implemented state). `tsc --noEmit` and `npm run build` clean.


### Added — Phase 4A evaluation framework

- `app/evaluation/` — dataset model with mandatory ground-truth basis and
  content fingerprint, an 8-document/22-case corpus spanning nine behavioural
  categories, precisely defined metrics, a real-PostgreSQL harness, a fair
  conventional-RAG baseline, a reproducible runner and a generated report.
- `python -m app.evaluation.run` writes per-run artefacts: `results.json`,
  `dataset.json`, `report.md`.
- `docs/EVALUATION.md` — dataset, metric definitions, results, calibration
  procedure and an explicit list of what could not be measured.
- `tests/unit/test_evaluation.py` (26 tests) and
  `tests/integration/test_evaluation_live.py` (12 tests against real PostgreSQL).

### Fixed — retrieval returned nothing for natural-language questions

`websearch_to_tsquery` ANDs every term, so a question had to contain all of its
words in one chunk. Measured effect: **73.7% of answerable evaluation cases
returned no evidence**, which the generation stage then correctly refuses to
answer from. Migration `20260104000000_retrieval_query_relaxation.sql` matches
strictly first and falls back to a term-OR parse only when the conjunction
matches nothing. Recall@5 rose 0.211 → 0.605 and MRR 0.263 → 0.789 on the corpus
as it then stood. Covered by a regression test.

### Changed

- `VerificationThresholds` makes the ADR-0012 boundaries (0.70 / 0.45)
  configurable and validated per service, instead of module-level constants.
  Their uncalibrated status is now stated in the code and in
  `docs/EVALUATION.md`.
- Migration count 10 → 11; migration/RLS checks 221 → 223.

### Known limitations recorded

- Lexical strength is **not** an adequate evidence-sufficiency signal: an
  answerable case scored below an unanswerable one, so the calibrated 0.25 floor
  removes missed abstentions but refuses ~27% of answerable questions.
- The conventional baseline outperforms MNEMOS on recall, MRR and nDCG on this
  corpus, because MNEMOS correctly hides superseded material by default. This is
  a negative result for MNEMOS and is reported as one.
- No answer-level metric was measured: no model provider is reachable.


### Added

- **Phase 3D — agents and orchestration.** Four roles over real services:
  `orchestrator` (plan and trace), `researcher` (retrieval), `analyst` (grounded
  generation) and `critic` (verification). Capability isolation is enforced by
  construction and re-checked at each seam, so an agent cannot do another's job:
  the analyst cannot verify its own answer and the critic cannot rewrite one.
  The plan is fixed before execution and stored with the run; a step row is
  written only after the work it describes has completed. Skipped is recorded as
  skipped with a reason, never as succeeded. Schemas: `orchestration_runs`,
  `agent_runs`, `agent_steps` (RLS, server-side writes only — `authenticated`
  may read a trace but never author one) and `orchestration_trace(uuid)`.
  Endpoints: `POST /agents/workspaces/{id}/ask`, `GET /agents/orchestrations/{id}`,
  `GET /agents/workspaces/{id}/orchestrations`.
- **Phase 3C — verification, corrections and conflict detection.**
  `claim_verifications`, `knowledge_corrections`, `knowledge_conflicts`,
  `apply_knowledge_correction(uuid, uuid)` and the `current_provenance` view.
  Two verification methods (`lexical_overlap` deterministic and free,
  `model_judgement` failing closed on provider error); `unverified` is kept
  distinct from `unsupported`; `reliability` is null when nothing was checked.
  Corrections are proposed, reviewed and applied as three auditable acts, with
  self-approval refused by service *and* database trigger, and application
  creating a revision rather than overwriting history. Endpoints under `/memory`.
- **Phase 3B — grounded generation with citation binding.**
  `conversations`, `messages`, `answers`, `claims`, `claim_citations`,
  `execution_records`. No evidence means no model call and an honest abstention;
  an unknown citation is rejected and nothing is stored; provider failure
  returns 502 with a `failed` execution record and no answer row. Endpoints
  under `/conversations`.
- **Phase 3A — hybrid retrieval.** Lexical and semantic search fused, with
  configurable weights, `include_superseded` and information-status filtering,
  over `hybrid_search_chunks(...)`. Endpoints under `/retrieval` and
  `POST /knowledge/workspaces/{id}/search`.
- Docs: `docs/RETRIEVAL_AND_GROUNDING.md`, `docs/AGENTS.md`-level role
  description inside `ARCHITECTURE.md`, ADR-0012 (verification policy) and
  ADR-0013 (agent capability isolation).

### Fixed

- Transport failures (DNS, connect, timeout) escaped the completion provider as
  raw `httpx` exceptions, so a caller catching `CompletionError` would have
  missed them and the API would have returned a 500. They now convert.
- Exhausted retries reported only "did not respond", discarding the cause. A 429
  is now reported as rate limiting and a 5xx as unavailability.
- An answer that asserted claims with no verification available reported as
  undegraded. It now reads as degraded with the plan's reason, because
  "unchecked" must not look like "checked and fine".
- `apply_knowledge_correction` relied on `auth.uid()` to identify its caller,
  which does not work inside `SECURITY DEFINER`. It now takes the actor
  explicitly and re-checks contributor membership, and the `SECURITY DEFINER`
  search path is pinned.
- The `current_provenance` view had no grant of its own, so real users got
  "permission denied" while the owner-run seed path worked. A view does not
  inherit its base table's privileges.

### Known limitations

- **No live model or embedding call has ever been made.** Every provider-level
  test uses a mock transport: request shape, error mapping and usage parsing are
  proven; model behaviour and answer quality are not. Measurement is Phase 4A.
- No live Supabase project. RLS is verified against a local reconstruction of
  Supabase's roles and auth functions, not the hosted service. pgvector support
  on the eventual target is unconfirmed.
- Frontend is unchanged since the redesign: 119 tests over 11 files.
  `EvidencePanel` exists but is not yet wired to the new answer endpoints, and
  the composers remain disabled.

- **Phase 2A — provenance-aware knowledge schema.** Two migrations add
  `sources`, `document_versions`, `extracted_contents`, `extracted_pages`,
  `chunks` and `provenance_records` with composite same-workspace foreign
  keys, a one-current-version partial unique index, sha256/offset CHECK
  constraints, a version-immutability trigger, chunk↔source and
  provenance↔chunk agreement triggers, and `resolve_chunk_provenance(uuid)`
  (`SECURITY INVOKER`). RLS is enabled and forced on every table; users may
  read but never write derived data.
- Domain layer: `app/domain/knowledge.py` (`Source`, `DocumentVersion`,
  `Chunk`, `SourceLocation`, `ChunkDraft`, `ProvenanceReference` and the
  status enums). Repositories: `SupabaseSourceRepository`,
  `SupabaseChunkRepository` plus protocols and a `KnowledgeService`.
- API: `GET /api/v1/knowledge/workspaces/{id}/sources`,
  `GET /api/v1/knowledge/sources/{id}`, `/versions`, `/chunks`,
  `GET /api/v1/knowledge/chunks/{id}/provenance`,
  `DELETE /api/v1/knowledge/sources/{id}`.
- Docs: `docs/DATABASE_SCHEMA.md`, `docs/PROVENANCE_MODEL.md`,
  `docs/DATA_DICTIONARY.md` (Mermaid ER diagrams, invariants, transitions).

- **Phase 2B — controlled ingestion.** `IngestionPipeline` with an ordered,
  failure-aware lifecycle; content-based format detection (magic bytes and
  decoding, never the declared MIME type); PDF/Markdown/plain-text extractors
  with page and heading offsets preserved; notes as versioned sources;
  idempotency keys; storage-object cleanup on failure and on deletion.
- Endpoints: `POST /knowledge/workspaces/{id}/sources/upload`,
  `POST /knowledge/workspaces/{id}/sources/note`,
  `POST /knowledge/sources/{id}/versions/upload`,
  `POST /knowledge/sources/{id}/versions/note`,
  `GET /knowledge/sources/{id}/download`, `DELETE /knowledge/sources/{id}`.
- Frontend: real submission panel, source list with honest statuses, detail
  panel with version history, status legend. `/sources` is now the workspace.
- Dependencies added: `python-multipart==0.0.9`, `pypdf==7.1.0`.

- **Phase 2C — chunking and vector indexing.** Deterministic
  `paragraph-window` chunking (900 / 150 / 4000) with the configuration
  recorded per chunk; an embedding adapter isolated from the chat provider
  (refuses chat endpoints, validates dimensions, bounded retries, usage
  capture); `chunk_embeddings` with a configured `vector(N)`, HNSW cosine
  index, forced RLS and `match_chunks()` as `SECURITY INVOKER`;
  `IndexingService` with resume-on-retry and an explicit re-index; two
  endpoints and UI controls showing chunk ranges and pages.
- ADR-0010 records the embedding-provider separation. `docs/CHUNKING_AND_
  INDEXING.md` records the measured parameter justification.

- **Product redesign.** Original visual identity — warm charcoal surfaces with
  exactly three semantic hues (teal = live intelligence, brass = the human
  record, rose = conflict), Instrument Serif display type, Inter UI, JetBrains
  Mono for every literal value. Self-hosted fonts; contrast verified from the
  token file.
- **Public landing page** at `/` (product moved to `/app`): hero with a
  lazy-loaded Three.js knowledge network and a designed SVG fallback, a
  seven-step pipeline walkthrough with per-step Implemented/Planned labels, an
  interactive agent topology, and a provenance showcase with revision states.
- **Product shell**: grouped navigation, collapsible rail, workspace context,
  page transitions, and a keyboard command palette (⌘K) validated as a proper
  combobox/listbox.
- **Redesigned screens**: dashboard (real corpus KPIs, proportional pipeline,
  refuses to draw without a session), three-column knowledge workspace with
  filtering, agent contract inspector, conversation modes with an execution
  timeline explicitly marked "Planned — not run", and an evidence drawer on the
  real provenance endpoint.
- **Motion system**: shared duration/easing tokens mirrored between CSS and JS;
  reveal/stagger/page primitives, cursor spotlight, tilt, magnetic buttons — all
  reduced-motion aware at a single policy point.
- **Accessibility**: axe audit extended to the landing page, palette and agent
  directory (0 violations); three real bugs found and fixed (unnamed listbox,
  invalid listbox children, duplicate controls mounted for desktop and hidden
  with CSS).
- ADR-0011 and `docs/DESIGN_SYSTEM.md` record the decisions and the exact
  verification boundary.

### Verified

- `scripts/verify-migrations.py`: **126 passed, 0 failed** against real
  PostgreSQL 16, including 47 new knowledge-schema and RLS checks.
- Backend: `pytest` **247 passed** with `pgserver` installed; the 5 real-PostgreSQL
  integration tests skip cleanly without it;
  `ruff` + `ruff format --check` clean; `mypy app` strict clean (44 files).
- Frontend: `tsc --noEmit` clean, `vitest` **119 passed** (11 files),
  `npm run build` succeeded, 10 axe audits with 0 violations. Bundle: entry
  151 kB, `three` isolated at 472 kB and absent from first paint.
- Environment finding: pgvector **0.6.2 is available** in the local harness
  (HNSW included). `pg_trgm` is **not**, so lexical retrieval must use core
  PostgreSQL full-text search. Neither has been confirmed on a live Supabase
  project.

- Phase 0 engineering foundation: repository structure, environment
  templates, `.gitignore`, and control documents (README, AGENTS, RULES,
  ARCHITECTURE, REQUIREMENTS, DECISIONS, TRACKER, CHANGELOG,
  CONTRIBUTING).
- Architecture Decision Records ADR-0001–0006 (Supabase platform,
  frontend, backend, OpenRouter, repository architecture, pgvector).
- Supabase foundation documentation (connection strategy, migrations,
  RLS strategy, storage strategy) — no schema created.
- OpenRouter foundation documentation (adapter boundary, configuration) —
  no model calls made.
- Backend health-check skeleton (FastAPI `GET /health`, config validation,
  structured logging, typed errors) with foundation tests.
- Frontend placeholder shell (React + Vite + TypeScript) with Vitest
  smoke test.
- Quality automation: Ruff, mypy (strict), pre-commit, GitHub Actions CI
  (lint, type-check, tests, build).

## [0.1.0] — Phase 1

Application foundation, Supabase infrastructure and responsive shell.

### Added
- Backend layered architecture: application factory with lifespan, versioned
  `/api/v1` routing, typed configuration with placeholder detection,
  canonical error envelopes, `X-Request-ID` correlation, services and schemas
  separated from routes, OpenAPI docs.
- Health (`/api/v1/health`) and readiness (`/api/v1/ready`) endpoints that
  report integration presence without exposing values.
- Supabase JWT verification (HS256, `sub` + `exp` required, `alg:none`
  rejected) and an authenticated dependency chain.
- Repository interfaces with Supabase implementations for profiles,
  workspaces and preferences; no arbitrary SQL entry point exists.
- Authenticated endpoints: `GET/PATCH /me`, `GET/PUT /me/preferences`,
  workspace list/create/read/update/delete, workspace members.
- Three idempotent migrations: foundational schema, RLS policies, private
  `sources` storage bucket.
- Four tables (`profiles`, `workspaces`, `workspace_members`,
  `user_preferences`) with FKs, checks, indexes and timestamp triggers.
- Signup bootstrap trigger provisioning profile, preferences, default
  workspace and owner membership.
- RLS enabled and forced on every table; deny-by-default; helper functions
  (`is_workspace_member`, `has_workspace_role`) `SECURITY DEFINER` with
  pinned `search_path`.
- `scripts/verify-migrations.py`: runs all migrations against a real
  PostgreSQL 16 instance with a Supabase-compatible `auth` shim and asserts
  62 checks (schema, idempotency, triggers, isolation, anon denial, storage).
- Frontend design system: colour (light + dark), typography, spacing,
  radius, border, shadow, motion and breakpoint tokens.
- Application shell: collapsible desktop sidebar, mobile drawer and bottom
  navigation, page header/container primitives, user menu with real sign-out.
- Centralized typed API client with timeouts, error normalization and bearer
  token support; dev proxy so the browser uses relative URLs.
- Auth provider with session tracking, password sign-in/sign-up and sign-out;
  explicit `unconfigured` state instead of a fake session.
- Shared conversation components supporting both orchestrated (Mode A) and
  direct specialist (Mode B) conversations, with disabled composer and an
  explicit reason — no fabricated AI responses.
- Agent directory presenting all four planned roles with responsibilities
  and boundaries, labelled as planned.
- Knowledge workspace structure, working theme settings, planned-area
  placeholder, 404 page.
- ADR-0007 (API conventions), ADR-0008 (Supabase access layering),
  ADR-0009 (styling approach).

### Changed
- `.gitignore`: Python `lib/` ignore scoped to `backend/` so frontend
  `src/lib` is tracked (bug found and fixed during Phase 1A).
- Frontend TypeScript target raised to ES2022.

### Fixed
- Health/readiness no longer report template placeholders as configured
  integrations.

## [0.0.1] — 2026-11-15

- Initial commit: repository created with a placeholder `README.md`.
