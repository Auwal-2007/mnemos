# MNEMOS — Contributing

## Workflow

1. Read [AGENTS.md](AGENTS.md) and [RULES.md](RULES.md) before starting.
2. Check [TRACKER.md](TRACKER.md) for the current phase and task.
3. Work incrementally: one verified layer at a time. Define acceptance
   criteria before coding.
4. Create a branch: `type/short-description` (e.g. `feat/knowledge-ingestion`).
5. Implement, test, and update documentation in the same change.
6. Run all checks locally (see below). CI must be green before merge.
7. Open a pull request with a description covering: what, why, how,
   decisions, how to test, limitations, and requirement/ADR traceability.

## Local checks

```bash
# Backend
cd backend
ruff check . && ruff format --check .
mypy app
python -m pytest -q

# Frontend
cd frontend
npm test -- --run
npm run typecheck && npm run build

# Environment template
cd .. && python3 scripts/check-env.py
```

## Git conventions

- Commits: `type: short description` (imperative). Types: `chore`, `docs`,
  `build`, `ci`, `test`, `feat`, `fix`, `refactor`.
- One concern per commit. Never commit secrets, `.env`, generated files,
  or unrelated changes. Never force-push.

## Code quality expectations

- Python: Ruff + mypy strict. TypeScript: strict mode. No `any`, no
  disabled linters to silence failures.
- No hardcoded secrets or model IDs. No arbitrary SQL from agents.
- Tests for every implementation stage; no fake tests.

## Database changes

- Only via versioned migrations in `supabase/migrations/` with review.
  See `docs/supabase/README.md`.

## Documentation

- Update relevant docs with every change (what, why, how, configuration,
  testing, limitations, next steps). Keep [TRACKER.md](TRACKER.md) current.
- Significant decisions require an ADR in `docs/adr/`.
