# Phase 1B — Supabase Integration and Database Architecture

**Status:** Implementation complete and locally verified. **Remote verification pending credentials.**
**Date:** 2026-11-15

## Honest status split

| Area | Local | Remote |
|---|---|---|
| Migration SQL | ✅ applied to real PostgreSQL 16, idempotent | ⏳ not applied to a Supabase project |
| RLS policies | ✅ 62 assertions pass against real PostgreSQL | ⏳ not exercised through PostgREST |
| Signup trigger | ✅ verified (profiles, preferences, workspace, owner membership) | ⏳ GoTrue not exercised |
| Auth/JWT verification | ✅ 12 unit tests incl. forged/expired/`alg:none` | ⏳ no live token issued |
| Storage bucket & policies | ✅ verified in harness (`storage` schema shim) | ⏳ Storage HTTP API not exercised |
| Backend data access | ✅ layered, typed, tested | ⏳ requires credentials to query a real project |

No claim is made that a Supabase project was contacted. It was not.

## Environment inspection

- Supabase CLI: not installed (`npx supabase` resolves 3.1.0 but Docker is absent,
  so `supabase start` cannot run here).
- No `.env` present; no credentials available.
- `supabase/config.toml` (from Phase 0) retained; migration directory reused.

## Database design

Four tables, all justified by the application foundation:

- `profiles` — needed to show identity in the UI without querying `auth.users`
- `workspaces` — the container every future knowledge entity will reference
- `workspace_members` — required because access is role-based, not owner-only
- `user_preferences` — persists the working theme setting

No speculative tables (no documents, chunks, embeddings, conversations,
messages, revisions, agents) were created. Verified by an explicit assertion
in the harness that scans `pg_tables`.

Full column-level reference: `docs/supabase/schema.md`.

## Authentication integration

- **Backend** (`app/infrastructure/auth.py`): HS256 verification with
  `sub` and `exp` required, audience verification disabled to match Supabase's
  token shape, `alg: none` rejected, errors never echo the failure reason.
- **Dependency chain** (`app/api/deps.py`): bearer extraction → verification →
  identity + user-scoped Supabase client → repositories → services.
- **Frontend** (`lib/auth/AuthProvider.tsx`): session tracking via
  `onAuthStateChange`, PKCE, password sign-in/sign-up, sign-out, and an
  explicit `unconfigured` state when credentials are missing.
- **Failure modes tested**: no header, wrong scheme, empty token, expired,
  forged signature, unsigned, missing `sub`.

## Row Level Security

Enabled **and forced** on all four tables. Policies are deny-by-default;
`anon` holds zero grants in `public`.

Verified behaviours (all against real PostgreSQL with an `auth.uid()` shim):

1. User A reads only their own workspace, profile and preferences.
2. User B cannot read A's workspace, preferences or membership rows.
3. `anon` is denied at the grant level on every `public` table.
4. B cannot `UPDATE` or `DELETE` A's workspace (0 rows affected, data intact).
5. A cannot create a workspace owned by B (RLS `WITH CHECK` blocks it).
6. A cannot modify B's profile or preferences.
7. A can update their own workspace and preferences.
8. Storage objects are isolated by `<user_id>/` path prefix; A cannot read or
   write B's folder.
9. `RLS helper functions` are executable by `authenticated` only.
10. `service_role` is the only non-superuser role with `BYPASSRLS`.

Helpers (`is_workspace_member`, `has_workspace_role`) are `SECURITY DEFINER`
with a pinned `search_path` to avoid recursive policy evaluation.

## Storage foundation

Private `sources` bucket, 50 MiB, MIME-restricted, user-scoped paths, no
public URLs, no UPDATE policy (objects immutable). Signed URLs are the only
download path. No upload UI or ingestion was built.

## Migration strategy

- Descriptive timestamped names; each migration is idempotent and re-runnable.
- `pgcrypto` is used only when available; `gen_random_uuid()` is core in
  PostgreSQL 13+, so the schema does not depend on the extension.
- Seed file intentionally inserts no user data (auth users must be created
  through the Auth API, not SQL).
- Rollback: documented per-migration below.
- Remote application requires explicit approval; **no remote database was
  modified**.

### Recovery

| Migration | Rollback |
|---|---|
| `..._initial_schema.sql` | `drop table public.workspace_members, public.user_preferences, public.workspaces, public.profiles cascade; drop function public.handle_new_user(), public.add_workspace_owner_membership(), public.set_updated_at() cascade; drop type public.workspace_role;` |
| `..._rls_policies.sql` | `drop function public.is_workspace_member(uuid), public.has_workspace_role(uuid, public.workspace_role[]);` plus `alter table ... disable row level security` if fully reverting |
| `..._storage_sources_bucket.sql` | `delete from storage.buckets where id='sources';` (after confirming no objects) — **destructive**, requires approval |

Rollback is destructive by nature; take a database backup before any remote
rollback, and never run it against production without explicit approval.

## Adapters and boundaries

`app/repositories/base.py` defines three `Protocol` interfaces. The Supabase
implementations translate PostgREST errors into domain errors
(`ForbiddenError` for RLS denials, `NotFoundError` for missing rows) and
never return rows the database refused to write.

There is no generic SQL entry point anywhere in the codebase.

## Dependencies added

`pyjwt` (backend token verification). Justification: Supabase tokens are
JWTs; verification requires a JWT library, and `pyjwt` is the mature,
widely used option already present transitively via `supabase`.

## Verification commands

```bash
backend/.venv/bin/python scripts/verify-migrations.py   # 62 checks, real PostgreSQL
cd backend && .venv/bin/python -m pytest -q             # 72 tests
cd frontend && npm test -- --run                        # 34 tests
```

## Known limitations

- No live Supabase project; PostgREST/GoTrue/Storage HTTP behaviour unverified.
- No automated test of the actual RLS-via-PostgREST path (would need a project).
- The harness shims `auth.uid()`; Supabase's implementation reads JWT claims
  the same way, but that equivalence is asserted, not observed remotely.
- No workspace invitation flow yet (membership table exists and is policed,
  but no endpoint adds members). Deliberately deferred.
