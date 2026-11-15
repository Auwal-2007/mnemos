# ADR-0002: Frontend — React + Vite + TypeScript

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

MNEMOS needs a responsive user interface supporting chat with the
orchestrator and specialists, knowledge management, evidence inspection,
and revision review. The interface must be type-safe, testable, and
maintainable by a small team.

## Decision

Use React 18 with Vite 5 and TypeScript 5 (strict mode), Vitest +
Testing Library for tests, and npm with a committed lockfile. The UI
communicates with the FastAPI backend over REST/JSON and uses the
Supabase publishable/anon key only for supported client contexts with
RLS enforced.

## Alternatives considered

- **Next.js (SSR):** rejected — server-side rendering adds complexity
  without a requirement; the backend is a separate FastAPI service and
  the UI is an authenticated SPA.
- **Plain JavaScript (no TypeScript):** rejected — type safety is a
  non-functional requirement (NFR-006); strict TypeScript catches
  contract errors early.
- **Vue/Svelte:** viable but rejected — React has the largest ecosystem
  and hiring pool for this project, and the team direction is
  React-based.

## Consequences

- Positive: mature toolchain, strong typing, fast builds, large
  ecosystem, easy testing with Vitest.
- Negative: SPA bundle size and client-side rendering constraints;
  mitigated by code-splitting in later phases.
- Replaceability: moderate — UI is decoupled from the backend via REST,
  so a future framework change is feasible.
