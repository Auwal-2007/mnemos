-- =========================================================================
-- MNEMOS — Phase 1B initial schema
--
-- Foundational, user-owned entities only:
--   * profiles              — one row per auth.users record
--   * workspaces            — a user's knowledge container
--   * workspace_members     — membership/roles for sharing
--   * user_preferences      — per-user application settings
--
-- Deliberately NOT created here: documents, notes, knowledge entries,
-- provenance, revisions, conversations, messages, embeddings. Those
-- belong to their own implementation milestones.
--
-- Conventions
--   * uuid primary keys (gen_random_uuid())
--   * timestamptz everywhere, created_at/updated_at defaulted
--   * foreign keys always explicit with an ON DELETE policy
--   * RLS enabled on every table in the companion migration
--
-- Idempotent: safe to re-run (IF NOT EXISTS / guarded DO blocks).
-- =========================================================================

-- gen_random_uuid() is provided by core PostgreSQL (13+); pgcrypto is not
-- required for that. Supabase also ships pgcrypto, but we deliberately
-- avoid depending on it here so migrations run on any modern PostgreSQL.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'pgcrypto') then
    create extension if not exists "pgcrypto" with schema extensions;
  end if;
exception
  when insufficient_privilege then
    raise notice 'pgcrypto not installed (insufficient privilege); gen_random_uuid() is built in';
end;
$$;

-- -------------------------------------------------------------------------
-- Shared trigger function: maintain updated_at
-- -------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

comment on function public.set_updated_at() is
  'Sets updated_at to now() on UPDATE. Attached to all mutable tables.';

-- -------------------------------------------------------------------------
-- profiles — application-level identity mirror of auth.users
-- -------------------------------------------------------------------------
create table if not exists public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  email         text,
  display_name  text check (display_name is null or char_length(trim(display_name)) between 1 and 80),
  avatar_url    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

comment on table public.profiles is
  'Public-facing user profile. One row per auth.users row, created automatically on signup.';
comment on column public.profiles.id is
  'Same identifier as auth.users.id. Cascades on user deletion.';

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- -------------------------------------------------------------------------
-- workspaces — the container for a user's knowledge
-- -------------------------------------------------------------------------
create table if not exists public.workspaces (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  name        text not null check (char_length(trim(name)) between 1 and 120),
  slug        text not null check (slug ~ '^[a-z0-9]([a-z0-9-]{1,48}[a-z0-9])$'),
  description text check (description is null or char_length(description) <= 2000),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint workspaces_owner_slug_unique unique (owner_id, slug)
);

comment on table public.workspaces is
  'A user-owned knowledge container. Ownership is the source of truth for access.';
comment on column public.workspaces.slug is
  'URL-safe identifier, unique per owner (not globally).';

create index if not exists workspaces_owner_id_idx on public.workspaces (owner_id);
create index if not exists workspaces_created_at_idx on public.workspaces (owner_id, created_at desc);

drop trigger if exists workspaces_set_updated_at on public.workspaces;
create trigger workspaces_set_updated_at
  before update on public.workspaces
  for each row execute function public.set_updated_at();

-- -------------------------------------------------------------------------
-- workspace_members — sharing/roles (justified: multi-user access needs
-- an explicit membership record; owner is also stored on workspaces)
-- -------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'workspace_role') then
    create type public.workspace_role as enum ('owner', 'editor', 'viewer');
  end if;
end;
$$;

create table if not exists public.workspace_members (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id      uuid not null references auth.users (id) on delete cascade,
  role         public.workspace_role not null default 'viewer',
  created_at   timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

comment on table public.workspace_members is
  'Explicit membership for shared workspaces. The owner is recorded here with role=owner.';

create index if not exists workspace_members_user_id_idx on public.workspace_members (user_id);

-- Keep membership consistent with ownership: the owner always has an
-- owner-role row, added automatically when a workspace is created.
create or replace function public.add_workspace_owner_membership()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  insert into public.workspace_members (workspace_id, user_id, role)
  values (new.id, new.owner_id, 'owner')
  on conflict (workspace_id, user_id) do update set role = 'owner';
  return new;
end;
$$;

drop trigger if exists workspaces_add_owner_membership on public.workspaces;
create trigger workspaces_add_owner_membership
  after insert on public.workspaces
  for each row execute function public.add_workspace_owner_membership();

-- -------------------------------------------------------------------------
-- user_preferences — basic application preferences, one row per user
-- -------------------------------------------------------------------------
create table if not exists public.user_preferences (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  theme      text not null default 'system' check (theme in ('system', 'light', 'dark')),
  locale     text not null default 'en' check (char_length(locale) between 2 and 10),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.user_preferences is
  'Per-user application preferences. Created on demand by the application service layer.';

drop trigger if exists user_preferences_set_updated_at on public.user_preferences;
create trigger user_preferences_set_updated_at
  before update on public.user_preferences
  for each row execute function public.set_updated_at();

-- -------------------------------------------------------------------------
-- New-user bootstrap: create a profile, default preferences and a first
-- workspace whenever Supabase Auth creates a user.
--
-- SECURITY DEFINER is required because auth.users inserts run as the
-- auth service. The function is owned by the migration role and has a
-- pinned search_path to prevent hijacking.
-- -------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  base_slug text;
  final_slug text;
  suffix int := 0;
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    nullif(trim(coalesce(new.raw_user_meta_data ->> 'display_name', '')), '')
  )
  on conflict (id) do nothing;

  insert into public.user_preferences (user_id)
  values (new.id)
  on conflict (user_id) do nothing;

  base_slug := lower(regexp_replace(
    coalesce(nullif(split_part(coalesce(new.email, ''), '@', 1), ''), 'workspace'),
    '[^a-z0-9]+', '-', 'g'
  ));
  base_slug := trim(both '-' from base_slug);
  if char_length(base_slug) < 3 then
    base_slug := 'workspace';
  end if;
  base_slug := left(base_slug, 40);

  final_slug := base_slug;
  while exists (
    select 1 from public.workspaces w where w.owner_id = new.id and w.slug = final_slug
  ) loop
    suffix := suffix + 1;
    final_slug := base_slug || '-' || suffix::text;
  end loop;

  insert into public.workspaces (owner_id, name, slug, description)
  values (new.id, 'Personal', final_slug, 'Your default MNEMOS workspace.')
  on conflict (owner_id, slug) do nothing;

  return new;
end;
$$;

comment on function public.handle_new_user() is
  'Bootstraps profile, preferences and a default workspace on signup. SECURITY DEFINER with pinned search_path.';

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
