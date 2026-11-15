# MNEMOS — Changelog

All notable changes are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
pre-release (`0.x.y`) until the first feature release.

## [Unreleased]

### Added

- Phase 0 engineering foundation: repository structure, environment
  templates, `.gitignore`, and control documents (README, AGENTS, RULES,
  ARCHITECTURE, REQUIREMENTS, DECISIONS, TRACKER, CHANGELOG,
  CONTRIBUTING).
- Architecture Decision Records ADR-0001–0006 (Supabase platform,
  frontend, backend, OpenRouter, repository architecture, pgvector).
- Supabase foundation documentation (connection strategy, migrations,
  RLS strategy, storage strategy) — no schema created.
- OpenRouter foundation documentation (adapter boundary, configuration) —
  no model calls made.
- Backend health-check skeleton (FastAPI `GET /health`, config validation,
  structured logging, typed errors) with foundation tests.
- Frontend placeholder shell (React + Vite + TypeScript) with Vitest
  smoke test.
- Quality automation: Ruff, mypy (strict), pre-commit, GitHub Actions CI
  (lint, type-check, tests, build).

## [0.1.0] — Phase 1

Application foundation, Supabase infrastructure and responsive shell.

### Added
- Backend layered architecture: application factory with lifespan, versioned
  `/api/v1` routing, typed configuration with placeholder detection,
  canonical error envelopes, `X-Request-ID` correlation, services and schemas
  separated from routes, OpenAPI docs.
- Health (`/api/v1/health`) and readiness (`/api/v1/ready`) endpoints that
  report integration presence without exposing values.
- Supabase JWT verification (HS256, `sub` + `exp` required, `alg:none`
  rejected) and an authenticated dependency chain.
- Repository interfaces with Supabase implementations for profiles,
  workspaces and preferences; no arbitrary SQL entry point exists.
- Authenticated endpoints: `GET/PATCH /me`, `GET/PUT /me/preferences`,
  workspace list/create/read/update/delete, workspace members.
- Three idempotent migrations: foundational schema, RLS policies, private
  `sources` storage bucket.
- Four tables (`profiles`, `workspaces`, `workspace_members`,
  `user_preferences`) with FKs, checks, indexes and timestamp triggers.
- Signup bootstrap trigger provisioning profile, preferences, default
  workspace and owner membership.
- RLS enabled and forced on every table; deny-by-default; helper functions
  (`is_workspace_member`, `has_workspace_role`) `SECURITY DEFINER` with
  pinned `search_path`.
- `scripts/verify-migrations.py`: runs all migrations against a real
  PostgreSQL 16 instance with a Supabase-compatible `auth` shim and asserts
  62 checks (schema, idempotency, triggers, isolation, anon denial, storage).
- Frontend design system: colour (light + dark), typography, spacing,
  radius, border, shadow, motion and breakpoint tokens.
- Application shell: collapsible desktop sidebar, mobile drawer and bottom
  navigation, page header/container primitives, user menu with real sign-out.
- Centralized typed API client with timeouts, error normalization and bearer
  token support; dev proxy so the browser uses relative URLs.
- Auth provider with session tracking, password sign-in/sign-up and sign-out;
  explicit `unconfigured` state instead of a fake session.
- Shared conversation components supporting both orchestrated (Mode A) and
  direct specialist (Mode B) conversations, with disabled composer and an
  explicit reason — no fabricated AI responses.
- Agent directory presenting all four planned roles with responsibilities
  and boundaries, labelled as planned.
- Knowledge workspace structure, working theme settings, planned-area
  placeholder, 404 page.
- ADR-0007 (API conventions), ADR-0008 (Supabase access layering),
  ADR-0009 (styling approach).

### Changed
- `.gitignore`: Python `lib/` ignore scoped to `backend/` so frontend
  `src/lib` is tracked (bug found and fixed during Phase 1A).
- Frontend TypeScript target raised to ES2022.

### Fixed
- Health/readiness no longer report template placeholders as configured
  integrations.

## [0.0.1] — 2026-11-15

- Initial commit: repository created with a placeholder `README.md`.
