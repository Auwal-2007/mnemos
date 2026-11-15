# MNEMOS Backend

FastAPI application (Phase 0 health skeleton only).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health
```

## Test & quality

```bash
python -m pytest -q
ruff check . && ruff format --check .
mypy app
```

## Structure

- `app/main.py` — FastAPI entry point (health only in Phase 0)
- `app/core/` — config, logging, errors
- `tests/` — unit, integration, API tests
