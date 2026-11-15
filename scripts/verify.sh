#!/usr/bin/env bash
# MNEMOS verification: run every check that can run without credentials.
#
#   ./scripts/verify.sh            # full run
#   ./scripts/verify.sh --quick    # skip the PostgreSQL migration harness
#
# Exits non-zero on the first failure. Checks that need a live Supabase
# project are documented in TRACKER.md and are not attempted here.
set -euo pipefail
cd "$(dirname "$0")/.."

QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

PY=backend/.venv/bin/python
[[ -x "$PY" ]] || { echo "ERROR: backend/.venv missing. See README setup." >&2; exit 1; }

echo "== 1/6 Environment template =="
python3 scripts/check-env.py

echo "== 2/6 Backend lint, format, types =="
(
  cd backend
  .venv/bin/ruff check --output-format=concise .
  .venv/bin/ruff format --check .
  .venv/bin/mypy app
)

echo "== 3/6 Backend tests =="
(cd backend && .venv/bin/python -m pytest -q)

if [[ $QUICK -eq 0 ]]; then
  echo "== 4/6 Database migrations and RLS (real PostgreSQL) =="
  "$PY" scripts/verify-migrations.py
else
  echo "== 4/6 Database migrations — SKIPPED (--quick) =="
fi

echo "== 5/6 Frontend tests, types, build =="
(
  cd frontend
  npm test -- --run
  npm run typecheck
  npm run build
)

echo "== 6/6 Secrets check =="
if git ls-files | grep -E '(^|/)\.env$'; then
  echo "ERROR: .env is tracked by git" >&2
  exit 1
fi
if git grep -nE 'SUPABASE_SERVICE_ROLE_KEY' -- 'frontend/**' 'frontend/*' 2>/dev/null; then
  echo "ERROR: service-role key referenced in frontend code" >&2
  exit 1
fi
if git grep -nE 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9._-]{20,}' -- ':!*.md' ':!*.lock' 2>/dev/null; then
  echo "ERROR: a JWT-like literal is committed" >&2
  exit 1
fi
echo "OK: no .env tracked, no service-role key in frontend, no committed JWTs"

echo
echo "All available checks passed."
echo "Not covered (needs Supabase credentials): remote migrations, GoTrue auth,"
echo "PostgREST RLS enforcement, Storage API. See TRACKER.md."
