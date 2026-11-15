# Phase 1A — Application Infrastructure and Backend Foundation

**Status:** Complete and verified
**Date:** 2026-11-15
**Branch:** `arena/39402bab-mnemos`

## Inspected baseline

Phase 0 delivered a FastAPI health skeleton (7 tests), a placeholder React
component, Ruff/mypy/Vitest, pre-commit and CI. All of it was preserved;
nothing was replaced without a documented reason.

## Implemented

### Backend (layered foundation)

| Concern | Location |
|---|---|
| Application factory + lifespan | `backend/app/main.py` |
| Versioned routing | `backend/app/api/v1/` (`api_router`) |
| Configuration + validation | `backend/app/core/config.py` |
| Error envelopes | `backend/app/core/errors.py` |
| Request correlation | `backend/app/core/middleware.py` |
| Response schemas | `backend/app/schemas/common.py` |
| Business logic | `backend/app/services/` |

Separation: routes validate and delegate → services hold logic → schemas
define contracts. No business logic sits in route handlers.

**API conventions**

- Base path: `/api/v1`; unversioned aliases for `/health` and `/ready` probes.
- Success: resource payload directly; collections `{"items": [...], "total": n}`.
- Errors: `{"error": {"code", "message", "request_id", "details"?}}` for every
  failure path (domain errors, validation, HTTP errors, unhandled exceptions).
- Correlation: `X-Request-ID` accepted (validated) or generated per request,
  echoed in the response header and in error payloads.
- Status: 200 read, 201 create, 204 delete, 400/401/403/404/422 client,
  5xx server. 422 carries field-level `details`.
- OpenAPI at `/openapi.json`, Swagger UI at `/docs`, ReDoc at `/redoc`.

**Endpoints**

- `GET /api/v1/health` — liveness: status, service, version, environment.
- `GET /api/v1/ready` — integration presence: `supabase`, `supabase_auth`,
  `openrouter` each `configured: true|false`. Never returns values.

**Truthfulness guard.** Placeholder values from `.env.example`
(`your-project-ref`, `placeholder`, `example.com`, …) are explicitly *not*
counted as configured. Verified live: with no `.env`, readiness reports all
three integrations as unconfigured.

### Frontend (foundation)

| Concern | Location |
|---|---|
| Entry point | `frontend/src/main.tsx` |
| Providers + error boundary | `frontend/src/app/` |
| Route table | `frontend/src/app/AppRoutes.tsx` |
| Navigation source of truth | `frontend/src/app/navigation.ts` |
| Design tokens | `frontend/src/styles/tokens.css` |
| Global styles | `frontend/src/styles/global.css` |
| API client | `frontend/src/lib/api/` |
| Auth context | `frontend/src/lib/auth/` |
| UI primitives | `frontend/src/components/ui/` |
| Layout | `frontend/src/components/layout/` |
| Conversation components | `frontend/src/components/conversation/` |
| Feature pages | `frontend/src/features/` |

Routing: `react-router-dom` v6, one `AppShell` layout route with nested
pages, `/sign-in` outside the shell. Navigation items carry
`status: 'available' | 'planned'` so unimplemented destinations are labelled
rather than faked.

Design system: CSS custom properties for colour (light + dark), typography,
spacing, radius, borders, shadows, motion and layout widths. Dark is the
default identity; light is first-class. Theme preference
(`system` / `light` / `dark`) persists to `localStorage`. Breakpoints
360/390/768/1024/1440 mirrored in `styles/tokens.ts`.

API client: single `request()` path with base-URL resolution, `AbortController`
timeouts (15 s default, overridable), typed `ApiError` with
`code`/`status`/`requestId`/`isRetryable`, envelope parsing, optional bearer
token, and `credentials: 'omit'`. Components never call `fetch` directly.

Loading/empty/error conventions: `LoadingState`, `EmptyState` (with icon,
description, optional action), `ErrorState` (message + request reference +
retry), `Spinner`, `Button.loading`, `ErrorBoundary` for render failures.

### Developer experience

- `npm run dev` runs Vite on `0.0.0.0:5173` and proxies `/api` to the
  backend (`VITE_DEV_BACKEND_URL`, default `http://127.0.0.1:8000`), so the
  browser uses relative URLs and there are no CORS problems in development.
- `uvicorn app.main:app --reload` serves the API on `0.0.0.0:8000`.
- Ruff, mypy (strict), Vitest, `tsc --noEmit`, production build all wired.

## Verification (actual results)

| Check | Result |
|---|---|
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| `mypy app` (strict) | Passed — 14 source files |
| `pytest` | **27 passed** |
| `npm run typecheck` | Passed |
| `npm test -- --run` | **23 passed** (4 files) |
| `npm run build` | Passed — 444 kB JS / 43 kB CSS (127/7 kB gzip) |
| Backend live: `GET /health` | `{"status":"ok",...}` |
| Backend live: `GET /api/v1/ready` | All integrations `false` (truthful) |
| Backend live: `GET /docs`, `/openapi.json` | 200 |
| 404 from backend | Canonical error envelope |
| Proxy: `GET :5173/api/v1/health` | 200, backend payload |
| SPA deep links `/agents`, `/conversations/agent/retrieval` | 200 |
| `.env` not tracked | Verified |

## Decisions

- **Ruff `B008` ignored for `app/api/**`** — FastAPI's dependency injection
  requires `Depends()` in argument defaults; the rule conflicts with the
  framework's idiom. Documented in `pyproject.toml`.
- **Placeholder detection in config** — readiness must not claim an
  integration is configured because a template value exists.
- **Relative API base (`/api/v1`) with a dev proxy** — avoids hardcoded URLs
  and CORS coupling; production can override with `VITE_API_BASE_URL`.
- **No CSS Modules** — plain per-component stylesheets with a strict BEM-ish
  naming convention (`block__element`, `block--modifier`) keep class names
  readable and avoid build-time hashing complexity at this stage.

## Not done in 1A (by design)

Supabase connectivity, database schema, RLS, storage, and AI execution.
Phase 1B covers the first four.

## Limitations

- No automated visual/responsive regression tooling; responsive behaviour is
  covered structurally in CSS and manually at the required widths.
- The bundle is not code-split yet; acceptable at this size, revisit when
  feature routes grow.
