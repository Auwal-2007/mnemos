# Supabase Foundation

Supabase is MNEMOS's managed PostgreSQL platform (database, Auth,
Storage, Row Level Security, migrations, pgvector). No separate
PostgreSQL server is provisioned. **No production schema was created in
Phase 0.**

## Connection strategy

| Context | Credential | Notes |
|---|---|---|
| Browser / public client | Publishable (anon) key | Only with RLS enforced |
| Backend (privileged ops) | Secret (service-role) key | Server-side only, never in browser code |
| Migrations / admin tooling | Direct Postgres connection string | Server-side only |

Environment variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL` (see `.env.example`).

## CLI approach

```bash
npm install -g supabase        # or use the Docker/local stack
supabase init                  # already scaffolded in supabase/
supabase link --project-ref <ref>
supabase db push               # apply migrations
supabase db diff               # review schema drift
supabase start                 # local stack (optional)
```

## Migrations

- Versioned SQL files in `supabase/migrations/`, named
  `YYYYMMDDHHMMSS_description.sql`.
- Every migration is reviewed before applying. No destructive migrations
  without backup and approval. No undocumented dashboard-only changes.
- Seed data (if any) lives in `supabase/seed.sql` and is for development
  only — never production personal data.

## RLS and Storage

- RLS strategy: [rls-strategy.md](rls-strategy.md)
- Storage strategy: [storage-strategy.md](storage-strategy.md)

## Phase 0 status

- [x] Connection strategy documented
- [x] Migration conventions documented
- [x] RLS and Storage strategies documented
- [ ] Supabase project provisioned (user action)
- [ ] Initial schema migration (Phase 1)
- [ ] pgvector validation (ADR-0006)
