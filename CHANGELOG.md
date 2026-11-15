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

## [0.0.1] — 2026-11-15

- Initial commit: repository created with a placeholder `README.md`.
