# Database Schema — Phase 1

Foundational tables only. Knowledge, provenance, conversations and agents
are deliberately **not** modelled yet.

Migrations: `supabase/migrations/`
- `20260101000000_initial_schema.sql` — tables, triggers, signup bootstrap
- `20260101000100_rls_policies.sql` — RLS, helper functions, grants
- `20260101000200_storage_sources_bucket.sql` — private `sources` bucket

## Entity relationship

```
auth.users (Supabase managed)
   │ 1:1 (cascade)
   ├──────────────► public.profiles
   │ 1:1 (cascade)
   ├──────────────► public.user_preferences
   │ 1:N (cascade, owner_id)
   └──────────────► public.workspaces ──1:N──► public.workspace_members
                          │                          │
                          └──────────────────────────┘ (workspace_id, user_id) PK
                                                     │
                                            auth.users (user_id, cascade)
```

## public.profiles

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK, FK → `auth.users.id` ON DELETE CASCADE |
| `email` | `text` | nullable (mirrored from auth) |
| `display_name` | `text` | nullable, 1–80 chars when present |
| `avatar_url` | `text` | nullable |
| `created_at` | `timestamptz` | NOT NULL DEFAULT `now()` |
| `updated_at` | `timestamptz` | NOT NULL DEFAULT `now()`, trigger-maintained |

Created automatically by `handle_new_user()` on signup.

## public.workspaces

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK DEFAULT `gen_random_uuid()` |
| `owner_id` | `uuid` | NOT NULL, FK → `auth.users.id` ON DELETE CASCADE |
| `name` | `text` | NOT NULL, 1–120 chars |
| `slug` | `text` | NOT NULL, regex `^[a-z0-9]([a-z0-9-]{1,48}[a-z0-9])$` |
| `description` | `text` | nullable, ≤ 2000 chars |
| `created_at`/`updated_at` | `timestamptz` | NOT NULL, trigger-maintained |

Unique: `(owner_id, slug)` — slugs are unique per owner, not globally.
Indexes: `workspaces_owner_id_idx`, `workspaces_created_at_idx (owner_id, created_at desc)`.

## public.workspace_members

| Column | Type | Constraints |
|---|---|---|
| `workspace_id` | `uuid` | FK → `workspaces.id` ON DELETE CASCADE, PK part |
| `user_id` | `uuid` | FK → `auth.users.id` ON DELETE CASCADE, PK part |
| `role` | `workspace_role` | enum `owner`/`editor`/`viewer`, default `viewer` |
| `created_at` | `timestamptz` | NOT NULL DEFAULT `now()` |

Composite PK `(workspace_id, user_id)`. Index on `user_id`.
The workspace owner is inserted here with role `owner` by trigger
`workspaces_add_owner_membership`.

## public.user_preferences

| Column | Type | Constraints |
|---|---|---|
| `user_id` | `uuid` | PK, FK → `auth.users.id` ON DELETE CASCADE |
| `theme` | `text` | NOT NULL DEFAULT `'system'`, CHECK in (`system`,`light`,`dark`) |
| `locale` | `text` | NOT NULL DEFAULT `'en'`, 2–10 chars |
| `created_at`/`updated_at` | `timestamptz` | NOT NULL, trigger-maintained |

## Storage: `sources` bucket

| Property | Value |
|---|---|
| Public | **false** |
| Size limit | 50 MiB |
| Allowed types | PDF, plain text, Markdown, JSON, DOCX, ODT |
| Path convention | `<auth.uid()>/<filename>` |
| Policies | SELECT / INSERT / DELETE scoped to own folder; no UPDATE |
| Signed URLs | Required for download; no public URLs exist |

Phase 1 provisions the bucket only — no upload UI and no ingestion.

## Functions and triggers

| Object | Purpose | Security |
|---|---|---|
| `set_updated_at()` | maintains `updated_at` | invoker |
| `handle_new_user()` | profile + preferences + default workspace on signup | SECURITY DEFINER, pinned `search_path` |
| `add_workspace_owner_membership()` | keeps owner membership consistent | SECURITY DEFINER, pinned `search_path` |
| `is_workspace_member(uuid)` | RLS helper | SECURITY DEFINER, STABLE, EXECUTE granted to `authenticated` only |
| `has_workspace_role(uuid, workspace_role[])` | RLS helper | SECURITY DEFINER, STABLE, EXECUTE granted to `authenticated` only |

Helpers are `SECURITY DEFINER` to avoid recursive RLS evaluation on
`workspace_members` (a policy on that table calling a function that reads
that table would otherwise recurse).

## Policy summary

| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| `profiles` | self or workspace colleague | (trigger only) | self | — (cascade) |
| `workspaces` | member | owner must be caller | owner or editor | owner |
| `workspace_members` | self or manager | manager | manager | manager, non-owner rows only |
| `user_preferences` | self | self | self | — (cascade) |
| `storage.objects` (`sources`) | own folder | own folder | none | own folder |

`anon` holds **no** table grants in `public`; all four tables have both
`ENABLE` and `FORCE ROW LEVEL SECURITY`.

## Verification

`scripts/verify-migrations.py` applies every migration to a real PostgreSQL
16 instance with a Supabase-compatible `auth` shim and asserts 62 checks
(schema shape, idempotency, trigger behaviour, read/write isolation, anon
denial, storage paths, privileged access). See `docs/phases/phase-1b-report.md`.

## Not verified here

Live Supabase connection, GoTrue token issuance, and the Storage HTTP API
require project credentials. They are untested, not assumed working.
