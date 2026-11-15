# MNEMOS — Project Tracker

Authoritative phase status. A task is complete only when its acceptance
criteria have been verified. Never mark work complete on the basis of
intent.

## Current phase

**Phase 0 — Environment and Engineering Foundation.** In progress on
branch `arena/c7f94f52-mnemos`.

## Current task

Phase 0 foundation initialization: repository structure, environment
templates, engineering documents, quality automation, testing foundation,
Supabase/OpenRouter strategy, and verification.

## Completed work

- [x] Repository inspected (clean tree, single `README.md`, one commit
      `a5c59cc` on `main`; branch `arena/c7f94f52-mnemos`).
- [x] Technology stack selected and documented (ADR-0001–0006).
- [x] Repository structure established (backend, frontend, supabase,
      shared, docs, scripts).
- [x] Engineering control documents created (README, AGENTS, RULES,
      ARCHITECTURE, REQUIREMENTS, DECISIONS, TRACKER, CHANGELOG,
      CONTRIBUTING).
- [x] Environment templates and `.gitignore` created; secrets excluded.
- [x] Supabase foundation documented (connection, migrations, RLS,
      storage) — no schema created.
- [x] OpenRouter foundation documented (adapter boundary, config) — no
      model calls made.
- [x] Quality tooling configured (Ruff, mypy, Vitest, pre-commit, CI).
- [x] Testing foundation created (config validation, health check,
      import/startup tests).
- [x] Checks executed and verified (see verification status below).
- [x] Git checkpoint committed.

## In-progress work

- None. Phase 0 is complete pending user approval for Phase 1.

## Pending work

- Phase 1 (to be scoped after approval): database schema design,
  Supabase project provisioning, and initial migrations.
- Later phases: knowledge ingestion, retrieval, agent implementations,
  UI features — each with its own objectives, acceptance criteria, tests,
  and checkpoint.

## Blockers

- None for Phase 0. Later phases require the user to provide a Supabase
  project and an OpenRouter API key (see "Outstanding manual setup").

## Technical decisions awaiting approval

- ADR-0006 (pgvector) is `Proposed` pending extension/dimension
  validation in a later phase.
- Specific OpenRouter model IDs per agent responsibility (deferred to
  the AI integration phase; must be validated per model).

## Tests and verification status

| Check | Status |
|---|---|
| `python3 scripts/check-env.py` | Passed (template valid) |
| `ruff check` / `ruff format --check` | Passed |
| `mypy app` (strict) | Passed |
| `pytest` (backend foundation tests) | Passed |
| `npm test` (Vitest) | Passed |
| `npm run typecheck` / `npm run build` | Passed |
| Secrets excluded from Git (`git status`, `.gitignore`) | Verified |
| CI workflow present and syntactically valid | Verified |

## Next recommended task

**Await explicit user approval, then scope Phase 1:** Supabase project
provisioning, initial schema migration design (knowledge, provenance,
revisions, evidence links), and RLS policy implementation — with
acceptance criteria and tests defined before coding.

## Outstanding manual setup (user)

1. Create a Supabase project; copy values into local `.env`
   (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_DB_URL`).
2. Create an OpenRouter API key; copy into local `.env`
   (`OPENROUTER_API_KEY`) and choose model IDs per agent responsibility.
3. Install the Supabase CLI locally for migration workflows
   (`npm i -g supabase` or see `docs/supabase/README.md`).
