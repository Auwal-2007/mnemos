# ADR-0005: Repository architecture

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

MNEMOS is developed incrementally by a small team over multiple phases.
The repository must reflect the selected architecture (React frontend,
Python backend, Supabase migrations, shared contracts) with clear
separation of concerns and no empty directories without purpose.

## Decision

Monorepo with top-level `backend/`, `frontend/`, `supabase/`,
`shared/`, `docs/`, and `scripts/` directories. Backend layers:
routes → services → repositories → Supabase. Frontend layers:
components/pages → services → API. Shared contracts in `shared/`.
Engineering control documents at the repository root. CI in
`.github/workflows/`.

## Alternatives considered

- **Separate repositories per component:** rejected — coordination
  overhead for a small team; monorepo simplifies versioning, CI, and
  cross-stack contracts.
- **Single mixed directory:** rejected — blurs boundaries and invites
  circular dependencies and scattered data access.

## Consequences

- Positive: single source of truth, atomic cross-stack changes, simple
  CI, clear layering.
- Negative: monorepo tooling discipline required (per-component
  lockfiles, scoped CI jobs).
- Replaceability: high — components can be extracted later if needed.
