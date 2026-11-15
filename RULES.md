# MNEMOS — Engineering Constitution (RULES.md)

The detailed engineering rules for MNEMOS. Where this document and
[AGENTS.md](AGENTS.md) overlap, the stricter rule applies.

## 1. Naming conventions

- **Python:** `snake_case` for modules, functions, variables; `PascalCase`
  for classes; `UPPER_SNAKE_CASE` for constants. Files: `snake_case.py`.
- **TypeScript:** `camelCase` for functions/variables; `PascalCase` for
  components/types; files: `PascalCase.tsx` for components, `camelCase.ts`
  for utilities.
- **Database:** `snake_case` plural tables (`knowledge_items`),
  `snake_case` columns, `pk_`/`fk_`/`idx_`/`uq_` prefixes for constraints
  and indexes. Migrations: `YYYYMMDDHHMMSS_description.sql`.
- **API:** REST paths in `kebab-case` (`/knowledge-items`), JSON fields in
  `camelCase` at the frontend boundary, `snake_case` in Python models.
- **Requirements:** stable IDs (`FR-001`, `NFR-001`) — never reuse or
  renumber. **ADRs:** `NNNN-title.md` in `docs/adr/`.
- **Git branches:** `type/short-description` (e.g. `feat/knowledge-ingestion`).

## 2. File organization

- One responsibility per file. Keep modules cohesive and files under ~400
  lines; split when a file mixes concerns.
- Backend: `app/` (application), `app/core/` (config, logging, errors),
  `app/api/` (routes), `app/services/` (business logic), `app/repositories/`
  (data access), `app/agents/` (agent contracts/orchestration),
  `app/models/` (domain + Pydantic schemas). Tests mirror `app/` under
  `tests/`.
- Frontend: `src/components/`, `src/pages/`, `src/services/` (API clients),
  `src/hooks/`, `src/types/`. No direct Supabase queries from components —
  go through `src/services/`.
- Shared contracts live in `shared/` and are versioned with the repo.

## 3. Dependency management

- Python: `backend/pyproject.toml` declares dependencies; `requirements.txt`
  is the pinned, reproducible install set. Bump deliberately, one concern
  per change, and record the reason.
- Node: `frontend/package.json` + committed `package-lock.json`. No
  `npm install` of unrelated packages.
- Prefer stable, mature libraries. New dependencies need a documented
  reason (problem, alternatives, trade-offs, replaceability).
- Never install every available package. Audit dependencies regularly
  (`pip-audit`, `npm audit`).

## 4. Error handling

- Define typed domain errors in `app/core/errors.py`; map them to HTTP
  status codes at the API boundary. Never leak stack traces, SQL, or
  internal paths to clients.
- Every error response: stable `code`, human `message`, `request_id` for
  traceability. Client errors (4xx) never expose server internals.
- Retry only retryable failures (timeouts, 5xx, rate limits) with bounded
  attempts and backoff. Never retry validation or auth failures.
- Agent/model failures must produce explicit error states, never silent
  fallbacks that fabricate answers.

## 5. Logging

- Structured logging (JSON in production, human-readable in development).
  Include `request_id`, `user_id` (when authenticated), and component name.
- Log levels: `DEBUG` (dev only), `INFO` (normal operations),
  `WARNING` (recoverable problems), `ERROR` (failures), `CRITICAL`
  (system-threatening).
- Never log: API keys, tokens, passwords, full document contents, or
  personal data beyond what is needed for the operation.
- Log model execution metadata (model ID, latency, token usage, cost where
  available) without logging prompt/response payloads verbatim.

## 6. Type safety

- Python: full annotations on public functions; mypy strict mode must pass.
  Pydantic v2 models at every trust boundary (API input/output, config,
  agent contracts, OpenRouter responses).
- TypeScript: `strict: true`; no `any` without a documented justification;
  `tsc --noEmit` must pass.
- No `# type: ignore` / `@ts-ignore` without a comment explaining why.

## 7. Input validation

- Validate at the boundary: API routes, file uploads, agent inputs,
  environment config. Reject invalid input with 422 + field errors.
- File uploads: enforce size limits, allow-listed MIME types, and content
  inspection. Store originals in private buckets; treat extracted text as
  untrusted.
- Sanitize all user-provided strings before rendering (XSS) and before
  embedding in prompts (prompt injection).

## 8. Security

- Secrets only via environment variables. `.env` is git-ignored; only
  `.env.example` with placeholders is committed.
- Supabase service-role key: server-side only. Publishable/anon key only
  with RLS enforced. Never expose privileged keys to browser code.
- Authentication via Supabase Auth; authorization enforced server-side and
  via RLS — never frontend-only.
- Rate limiting on API and model endpoints; CORS allow-listed origins.
- Dependency auditing in CI. Error messages sanitized. Sensitive-data
  minimization: collect and retain only what is needed.
- Prompt-injection: treat all documents and user input as untrusted;
  evidence must be cited, never assumed. No enterprise-grade security
  claims.

## 9. Database access

- Supabase PostgreSQL is the only database. No separate PostgreSQL server.
- Access pattern: API route → service → repository → Supabase client.
  No direct DB access from UI components or agents.
- Agents never execute arbitrary SQL. All operations are validated,
  parameterized, and ownership-checked.
- Schema changes only via versioned migrations in `supabase/migrations/`
  with review. No destructive migrations without backup and approval.
- Every user-owned table: `owner_id` (or equivalent) + RLS policy denying
  cross-user access by default.

## 10. API design

- REST + JSON, versioned under `/api/v1/`. OpenAPI generated by FastAPI.
- Consistent envelope: `{ "data": ..., "error": null }` or
  `{ "data": null, "error": { "code", "message", "request_id" } }`.
- Pagination: cursor-based for lists; stable sort keys.
- Idempotency keys for mutating operations where retries are expected.
- All timestamps ISO 8601 UTC. All IDs UUIDs.

## 11. AI integration

- Single centralized OpenRouter adapter (`app/agents/openrouter.py` in a
  later phase). No scattered HTTP calls to model endpoints.
- Model IDs from environment variables per agent responsibility. Never
  hardcoded. Capability checks (structured output, tool calling) before
  relying on them.
- Timeouts, bounded retries, error classification, rate-limit handling,
  usage/cost logging, and model ID recorded in every execution record.
- No paid model calls without explicit approval. No assumption that all
  models share capabilities.

## 12. Testing

- Layers: unit (`tests/unit/`), integration (`tests/integration/`), API
  (`tests/api/`), database, agent-contract, retrieval, provenance,
  end-to-end. Each layer has a clear purpose; do not blur them.
- Foundation tests only in Phase 0 (config validation, health check,
  imports). No fake tests. No coverage claims without running tests.
- Tests must be deterministic, isolated, and fast. No real model calls in
  CI — use recorded fixtures or mocks.
- Frontend: Vitest + Testing Library for components; Playwright for
  end-to-end when the UI exists.

## 13. Git commits

- Format: `type: short description` (imperative, ≤72 chars).
- Types: `chore`, `docs`, `build`, `ci`, `test`, `feat`, `fix`, `refactor`.
- One concern per commit. Reference requirement/ADR IDs where relevant
  (e.g. `feat: add knowledge ingestion (FR-003)`).
- Never commit secrets, `.env`, generated files, or unrelated changes.
- Never force-push. Never reset shared history.

## 14. Code review

- Every change is reviewed against: architecture boundaries, security,
  type safety, tests, documentation, and traceability.
- Reviewers check: no hardcoded secrets/models, no arbitrary SQL, no
  bypassed authorization, no unrecorded decisions.
- CI must be green before merge. No exceptions for "quick fixes".

## 15. Documentation

- Every task updates relevant docs: what, why, how, decisions,
  configuration, testing, limitations, next steps.
- Requirement → implementation → test traceability is mandatory.
- ADRs for significant decisions; phase reports per phase; tracker kept
  current. Documentation that disagrees with code is a bug.
