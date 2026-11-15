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

> **Current status — Phase 2C complete, plus a full product redesign.**
> The public site lives at `/` and the product at `/app`.
> Implemented: Supabase schema with forced RLS, document/note ingestion with
> text extraction and full provenance, deterministic chunking, and a vector
> index behind an isolated embedding adapter. **No retrieval or generation is
> implemented yet, and no model call has been made** — embeddings are not
> configured in this environment, so sources stop at "extracted" and the UI
> says they are not searchable.
>
> The interface was redesigned around an original visual identity ("warm
> archive, cold machine"): an editorial landing page, a grouped product shell
> with a command palette, and evidence inspection built on the real provenance
> API. See [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) and
> [ADR-0011](docs/adr/0011-visual-identity-and-motion.md).
>
> [TRACKER.md](TRACKER.md) is the authoritative phase status;
> [docs/phases/ui-redesign-report.md](docs/phases/ui-redesign-report.md) records
> the redesign and, importantly, what could not be verified without a browser.

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
- A Supabase project (required for authentication and data; the app runs
  without it and states clearly that the data layer is unconfigured)
- An OpenRouter API key (for the later AI phase; not used in Phase 1)

## Local setup

```bash
git clone https://github.com/Auwal-2007/mnemos.git
cd mnemos

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt ".[dev]"
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

Run the backend and frontend in two terminals.

```bash
# Terminal 1 — backend API on http://localhost:8000
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend on http://localhost:5173
cd frontend && npm run dev

# Verify environment template
python3 scripts/check-env.py
```

The frontend proxies `/api` to the backend (`VITE_DEV_BACKEND_URL`, default
`http://127.0.0.1:8000`), so the browser only uses relative URLs. Useful
endpoints:

| URL | Purpose |
|---|---|
| `http://localhost:5173/` | Application shell (home) |
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/openapi.json` | OpenAPI schema |
| `http://localhost:8000/api/v1/health` | Liveness |
| `http://localhost:8000/api/v1/ready` | Integration readiness (presence only) |

## API surface (Phase 1)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | no | Liveness |
| GET | `/api/v1/ready` | no | Which integrations are configured |
| GET | `/api/v1/me` | yes | Current profile |
| PATCH | `/api/v1/me` | yes | Update display name |
| GET | `/api/v1/me/preferences` | yes | Preferences |
| PUT | `/api/v1/me/preferences` | yes | Update theme |
| GET/POST | `/api/v1/workspaces` | yes | List / create |
| GET/PATCH/DELETE | `/api/v1/workspaces/{id}` | yes | Read / update / delete |
| GET | `/api/v1/workspaces/{id}/members` | yes | Membership |

Authenticated routes require `Authorization: Bearer <supabase-access-token>`
and return `401` with the standard error envelope otherwise. Identity always
comes from the verified token — never from the request body.

## Testing commands

```bash
# Backend
cd backend && python -m pytest -q
cd backend && ruff check . && ruff format --check . && mypy app

# Frontend
cd frontend && npm test -- --run
cd frontend && npm run typecheck && npm run build

# Database migrations + RLS (real PostgreSQL, no Docker or credentials needed)
backend/.venv/bin/python scripts/verify-migrations.py
```

`scripts/verify-migrations.py` boots a temporary PostgreSQL 16 instance,
creates a Supabase-compatible `auth` schema and roles, applies every
migration twice (proving idempotency), and asserts 62 checks covering schema
shape, the signup trigger, read/write isolation between two users, anonymous
denial and storage path scoping.

## Repository structure

```
mnemos/
├── backend/            # FastAPI: app/{api,core,domain,infrastructure,
│                       #   repositories,schemas,services}, tests/
├── frontend/           # React + Vite + TypeScript: app/, components/,
│                       #   features/, lib/, styles/, test/
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
under `supabase/migrations/`.

Phase 1 adds four foundational tables (`profiles`, `workspaces`,
`workspace_members`, `user_preferences`), a private `sources` storage bucket,
and RLS enabled and forced on every table. A signup trigger provisions a
profile, default preferences and a personal workspace.

To apply to a project of your own:

```bash
npx supabase link --project-ref <your-project-ref>
npx supabase db push          # additive; review the SQL first
```

Then set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` and
`SUPABASE_SERVICE_ROLE_KEY` in `.env` (server), plus `VITE_SUPABASE_URL` and
`VITE_SUPABASE_ANON_KEY` for the browser. **Never** put the service-role key
in a `VITE_*` variable.

Details: [docs/supabase/README.md](docs/supabase/README.md),
[schema.md](docs/supabase/schema.md),
[access-architecture.md](docs/supabase/access-architecture.md).

## OpenRouter setup overview

OpenRouter is the model-access and routing layer (not a model). Model IDs
are configured via environment variables; a centralized adapter will be
built in a later phase. **No model calls are made in Phase 1.**
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
