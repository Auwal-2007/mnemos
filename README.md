# MNEMOS

**Design and Implementation of a Provenance-Aware Multi-Agent Personal
Knowledge Management and Memory System.**

MNEMOS is a personal knowledge workspace and AI assistant. It lets users
submit and manage personal knowledge, ask questions about stored
information, inspect the sources supporting generated answers, review
revisions, identify conflicts, correct information, and receive explicit
insufficient-evidence responses — coordinated by a central orchestrator
and specialist agents (retrieval, memory management, evidence
verification) over a shared knowledge and provenance layer.

> **Current status — Phase 0 (Environment & Engineering Foundation).**
> This repository currently contains the engineering foundation only:
> architecture, rules, environment templates, quality automation, and a
> minimal health-check skeleton. **No product features have been
> implemented.** See [TRACKER.md](TRACKER.md) for the authoritative
> phase status and [docs/phases/phase-0-completion-report.md](docs/phases/phase-0-completion-report.md)
> for the Phase 0 completion report.

---

## Technology stack

| Layer | Selection | Why (summary) |
|---|---|---|
| Frontend | React 18 + Vite 5 + TypeScript 5 | Mature SPA toolchain, type safety, large ecosystem |
| Backend | Python 3.11+ + FastAPI + Pydantic v2 | Async API, OpenAPI, strong validation |
| Database | Supabase (managed PostgreSQL) | Managed Postgres, Auth, Storage, RLS, migrations |
| Vector search | pgvector (Supabase extension, to validate) | Co-located with relational data |
| AI access | OpenRouter (configurable model IDs) | Single routing layer, model replaceability |
| Testing | pytest + httpx; Vitest | Standard, fast, CI-friendly |
| Quality | Ruff, mypy (strict), pre-commit | Fast lint/format/type gates |
| CI | GitHub Actions | Lint, type-check, tests, build |

Full rationale and alternatives: [DECISIONS.md](DECISIONS.md) and
[docs/adr/](docs/adr/). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md).

## Prerequisites

- Python 3.11 or newer
- Node.js 20+ and npm 10+
- Git
- A Supabase project (for later phases; not required to run Phase 0 checks)
- An OpenRouter API key (for later phases; not required for Phase 0)

## Local setup

```bash
git clone https://github.com/Auwal-2007/mnemos.git
cd mnemos

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..

# Environment (placeholders only — fill in real values locally)
cp .env.example .env
```

## Environment configuration

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.
Supabase and OpenRouter setup: [docs/supabase/README.md](docs/supabase/README.md),
[docs/openrouter/README.md](docs/openrouter/README.md).

## Development commands

```bash
# Backend API (health check only in Phase 0)
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend (placeholder shell in Phase 0)
cd frontend && npm run dev

# Verify environment template
python3 scripts/check-env.py
```

## Testing commands

```bash
# Backend
cd backend && python -m pytest -q
cd backend && ruff check . && ruff format --check . && mypy app

# Frontend
cd frontend && npm test -- --run
cd frontend && npm run typecheck && npm run build
```

## Repository structure

```
mnemos/
├── backend/            # FastAPI application (health skeleton in Phase 0)
├── frontend/           # React + Vite + TypeScript shell (Phase 0)
├── supabase/           # Migrations, config, seed strategy
├── shared/             # Cross-stack contracts (future)
├── docs/               # ADRs, Supabase/OpenRouter guides, phase reports
├── scripts/            # Developer utilities
├── .github/workflows/  # CI (lint, type-check, tests, build)
├── AGENTS.md           # Permanent instructions for AI coding agents
├── RULES.md            # Engineering constitution
├── ARCHITECTURE.md     # Approved architecture
├── REQUIREMENTS.md     # Functional / non-functional requirements (stable IDs)
├── DECISIONS.md        # ADR index
├── TRACKER.md          # Phase tracker (authoritative status)
├── CHANGELOG.md        # Change log
└── CONTRIBUTING.md     # Development workflow
```

## Supabase setup overview

Supabase is the managed PostgreSQL platform (database, Auth, Storage, RLS).
No separate PostgreSQL server is provisioned. Migrations are versioned
under `supabase/migrations/`. No production schema was created in Phase 0.
Details: [docs/supabase/README.md](docs/supabase/README.md).

## OpenRouter setup overview

OpenRouter is the model-access and routing layer (not a model). Model IDs
are configured via environment variables; a centralized adapter will be
built in a later phase. No model calls were made in Phase 0.
Details: [docs/openrouter/README.md](docs/openrouter/README.md).

## Documentation links

- [AGENTS.md](AGENTS.md) — agent rules
- [RULES.md](RULES.md) — engineering constitution
- [ARCHITECTURE.md](ARCHITECTURE.md) — architecture
- [REQUIREMENTS.md](REQUIREMENTS.md) — requirements with stable IDs
- [DECISIONS.md](DECISIONS.md) — ADR index
- [TRACKER.md](TRACKER.md) — phase tracker
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow
- [docs/adr/](docs/adr/) — individual ADRs
- [docs/phases/phase-0-completion-report.md](docs/phases/phase-0-completion-report.md) — Phase 0 report
