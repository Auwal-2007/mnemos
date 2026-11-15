#!/usr/bin/env bash
# MNEMOS Phase 0 verification: run all available checks.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Environment template =="
python3 scripts/check-env.py

echo "== Backend: lint / format / types / tests =="
cd backend
ruff check .
ruff format --check .
mypy app
python -m pytest -q
cd ..

echo "== Frontend: tests / types / build =="
cd frontend
npm test -- --run
npm run typecheck
npm run build
cd ..

echo "== Secrets check =="
if git ls-files | grep -E '(^|/)\.env$'; then
  echo "ERROR: .env is tracked by git" >&2
  exit 1
fi
echo "OK: no .env tracked"

echo "All Phase 0 checks passed."
