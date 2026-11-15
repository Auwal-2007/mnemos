# ADR-0008 — Supabase access layering

**Status:** Accepted
**Date:** 2026-11-15

## Context

Supabase exposes PostgREST directly to any client holding the anon key. It
would be possible for the React app to query tables directly. That would
scatter authorization across the frontend, make AI-agent access impossible to
control, and put RLS alone between users and other users' data.

## Decision

All user-scoped data flows through:

```
component → lib/api → FastAPI route → service → repository → user-scoped client → RLS
```

1. **No direct table access from React.** The frontend calls the API only.
2. **Three clients** with distinct privilege (`docs/supabase/access-architecture.md`):
   user (token-bound), public (anon), service (RLS-bypassing, server-only).
3. **Routes use the user client**, built from the verified token, so RLS
   evaluates as that user.
4. **Repository interfaces** expose named operations; there is no
   `execute(sql)` method. Agents in later phases will call services, never SQL.
5. **The service layer owns authorization policy**; RLS is the backstop.
6. **Service-role key never reaches the browser** and is never injected as a
   route dependency.

## Alternatives considered

- **Direct Supabase from React** — fastest to build, but breaks the "agents
  never execute arbitrary SQL / services own authorization" constraint and
  makes privileged operations hard to audit.
- **Service-role everywhere on the backend** — simpler, but discards RLS as a
  safety net; one missing check would expose all users.
- **Separate ORM on a plain Postgres connection** — conflicts with the
  Supabase-first constraint and loses PostgREST/RLS integration.

## Consequences

- Two enforcement layers (service policy + RLS), verified independently.
- Slightly more code per feature; each feature gets a repository method,
  a service rule, and a route.
- Backend must hold `SUPABASE_JWT_SECRET` to verify tokens.
- Future agent tooling has a narrow, auditable surface to call.
