# MNEMOS — Agent Instructions

Permanent instructions for any AI coding agent working on MNEMOS.
These rules are enforceable: violating them is a defect, not a style choice.
If a task appears to require violating a rule, stop and document the
conflict in [TRACKER.md](TRACKER.md) instead of silently proceeding.

## 1. Project identity

MNEMOS is a provenance-aware multi-agent personal knowledge management and
memory system (see [ARCHITECTURE.md](ARCHITECTURE.md)). The approved
proposal defines identity, aim, objectives and scope; Chapters 1–3 define
terminology and methodology; the implementation blueprint defines
implementation guidance. Do not silently change research objectives. Do not
implement unrelated features. Do not claim the project is implemented when
it is not.

## 2. Architecture rules

- Build one verified layer at a time. Do not generate the complete
  application in one operation.
- Keep layers separated: schemas/migrations → repositories → services →
  API routes → agent orchestration. No direct database access scattered
  across unrelated components.
- No circular dependencies. No duplicated business logic. No unstructured
  agent communication.
- The orchestrator coordinates specialists; it must not duplicate their
  responsibilities. Direct specialist conversations must not bypass
  authorization, ownership boundaries, provenance, evidence validation,
  logging, or model configuration.
- Every agent must use controlled interfaces defining: identity,
  responsibility, input schema, output schema, available tools, permission
  boundaries, error states, execution metadata, and evidence-reference
  handling.
- No premature abstractions, no unnecessary microservices, no monolithic
  files.

## 3. Code quality standards

- Python: Ruff for lint + format, mypy in strict mode. Type-annotate all
  public functions. Pydantic v2 for validation at trust boundaries.
- TypeScript: strict mode, no `any` without justification, no unused vars.
- Prefer stable, mature, documented technologies. Do not install every
  available package. Pin dependencies; commit lockfiles.
- Keep functions small, modules cohesive, files focused.

## 4. Security requirements

- Never hardcode credentials, API keys, or model identifiers in business
  logic. Configuration comes from environment variables.
- Never expose the Supabase service-role/secret key to browser code.
  Privileged operations stay server-side.
- Never rely exclusively on frontend authorization. Enforce Row Level
  Security and server-side checks.
- Never log API keys, tokens, or full sensitive document contents.
- Validate all user input. Sanitize error messages. Treat all submitted
  documents as untrusted (prompt-injection risk).
- Do not claim enterprise-grade security or certification.

## 5. Testing requirements

- Every implementation stage ships with tests and documented acceptance
  criteria. Do not create fake tests to make CI pass. Do not claim coverage
  without running the tests.
- Test layers: unit, integration, API, database, agent-contract,
  retrieval, provenance, end-to-end (see `backend/tests/` and
  `frontend/` test conventions in [RULES.md](RULES.md)).
- Run the relevant checks before committing and report actual outcomes.

## 6. Documentation requirements

- Every task updates relevant documentation: what was built, why, how it
  works, decisions, configuration, how to test, limitations, next steps.
- Maintain traceability: requirement ID → implementation → tests.
- Architecture decisions go in [DECISIONS.md](DECISIONS.md) + `docs/adr/`.
- Phase status lives in [TRACKER.md](TRACKER.md). Never mark a task
  complete unless its acceptance criteria were verified.

## 7. Database access rules

- Supabase PostgreSQL is the only database. No separate PostgreSQL server,
  no second database without a documented, justified requirement.
- Agents never execute arbitrary SQL. All database operations go through
  validated application services and repositories.
- Schema changes only via versioned migrations in `supabase/migrations/`.
  Never rely on undocumented dashboard changes. Never run destructive
  migrations against production without review.
- Every user-owned resource has a clear ownership relationship and an RLS
  policy (see `docs/supabase/rls-strategy.md`).

## 8. Supabase rules

- Use Supabase Auth as the identity provider; design ownership boundaries
  from the beginning.
- Use the publishable/anon key only in supported client contexts with RLS
  enforced. Service-role key stays server-side.
- Original documents live in private Storage buckets with user-scoped
  paths, size/type validation, and signed URLs (see
  `docs/supabase/storage-strategy.md`).

## 9. Agent architecture constraints

- OpenRouter is the model-access layer, not a model. Use a centralized
  client adapter with environment-based keys, configurable model IDs per
  agent responsibility, timeouts, bounded retries, error classification,
  rate-limit handling, and usage/cost logging.
- Do not hardcode one model into the architecture. Do not assume every
  model supports the same capabilities (structured output, tool calling).
- Do not call paid model endpoints without explicit approval.

## 10. Git workflow

- Inspect `git status` and history before changing anything. Never
  overwrite existing user work, delete unknown files, reset the repo, or
  force-push.
- Descriptive commits following [CONTRIBUTING.md](CONTRIBUTING.md)
  (`chore:`, `docs:`, `build:`, `ci:`, `test:`, `feat:`, `fix:`).
- One concern per commit. Review the diff. Commit only verified work.
- Never commit secrets, `.env` files, generated files, or unrelated
  user changes.

## 11. Prohibited shortcuts

- No placeholder application functionality presented as working features.
- No fake health checks, fake tests, or fake metrics.
- No hardcoded secrets, model IDs, or credentials.
- No arbitrary SQL from agents. No direct DB access from UI components.
- No silent scope changes. No unrecorded architecture decisions.
- No `any`, no `# type: ignore` without justification, no disabled linters
  to silence failures.

## 12. Required completion reporting

Every task ends with a report covering: what was done, files changed,
commands run with actual outcomes, decisions made, limitations/risks, and
the recommended next step. Do not mark incomplete work as complete. Do not
hide failures. Do not proceed into the next phase without explicit user
approval.

## 13. Conventions note

This repository uses `AGENTS.md` as the single agent-rules file. If a
coding environment expects a different filename, follow `AGENTS.md` and do
not duplicate conflicting instructions elsewhere.
