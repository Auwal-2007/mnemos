-- =========================================================================
-- MNEMOS — Phase 1B Row Level Security
--
-- Model: deny by default. RLS is enabled on every table; access is granted
-- only through explicit policies. A user may touch a row when they own it
-- or hold a membership role that permits the operation.
--
-- Roles used by the policies:
--   * anon           — unauthenticated; NO access to any table here
--   * authenticated  — Supabase JWT-bearing users; scoped by policy
--   * service_role   — privileged server operations; bypasses RLS by
--                      design, so it is never shipped to the browser
--
-- Helper functions are SECURITY DEFINER with a pinned search_path and
-- are marked STABLE so planners can optimise repeated checks.
-- =========================================================================

-- -------------------------------------------------------------------------
-- Helpers
-- -------------------------------------------------------------------------

-- Membership check without recursive RLS evaluation (SECURITY DEFINER
-- bypasses RLS on workspace_members, preventing infinite recursion).
create or replace function public.is_workspace_member(target_workspace uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.workspace_members m
    where m.workspace_id = target_workspace
      and m.user_id = auth.uid()
  );
$$;

create or replace function public.has_workspace_role(
  target_workspace uuid,
  allowed_roles public.workspace_role[]
)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from public.workspace_members m
    where m.workspace_id = target_workspace
      and m.user_id = auth.uid()
      and m.role = any (allowed_roles)
  );
$$;

revoke all on function public.is_workspace_member(uuid) from public;
revoke all on function public.has_workspace_role(uuid, public.workspace_role[]) from public;
grant execute on function public.is_workspace_member(uuid) to authenticated;
grant execute on function public.has_workspace_role(uuid, public.workspace_role[]) to authenticated;

-- -------------------------------------------------------------------------
-- Enable RLS everywhere (deny by default)
-- -------------------------------------------------------------------------
alter table public.profiles          enable row level security;
alter table public.workspaces        enable row level security;
alter table public.workspace_members enable row level security;
alter table public.user_preferences  enable row level security;

-- Force RLS for table owners too, so an accidental owner connection
-- cannot silently bypass policies.
alter table public.profiles          force row level security;
alter table public.workspaces        force row level security;
alter table public.workspace_members force row level security;
alter table public.user_preferences  force row level security;

-- Baseline privileges: never to anon. Narrow grants only.
revoke all on public.profiles          from anon;
revoke all on public.workspaces        from anon;
revoke all on public.workspace_members from anon;
revoke all on public.user_preferences  from anon;

grant select, update on public.profiles         to authenticated;
grant select, insert, update, delete on public.workspaces        to authenticated;
grant select, insert, update, delete on public.workspace_members to authenticated;
grant select, insert, update on public.user_preferences          to authenticated;

-- -------------------------------------------------------------------------
-- profiles
--   read:   own profile, or profiles of people sharing a workspace
--   write:  own profile only (insert happens via the signup trigger)
-- -------------------------------------------------------------------------
drop policy if exists "profiles_select_self_or_coworker" on public.profiles;
create policy "profiles_select_self_or_coworker"
  on public.profiles
  for select
  to authenticated
  using (
    id = auth.uid()
    or exists (
      select 1
      from public.workspace_members me
      join public.workspace_members them on them.workspace_id = me.workspace_id
      where me.user_id = auth.uid()
        and them.user_id = profiles.id
    )
  );

drop policy if exists "profiles_update_self" on public.profiles;
create policy "profiles_update_self"
  on public.profiles
  for update
  to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

-- -------------------------------------------------------------------------
-- workspaces
--   read:   members
--   create: owner must be the caller
--   update: owner or editor
--   delete: owner only
-- -------------------------------------------------------------------------
drop policy if exists "workspaces_select_member" on public.workspaces;
create policy "workspaces_select_member"
  on public.workspaces
  for select
  to authenticated
  using (owner_id = auth.uid() or public.is_workspace_member(id));

drop policy if exists "workspaces_insert_own" on public.workspaces;
create policy "workspaces_insert_own"
  on public.workspaces
  for insert
  to authenticated
  with check (owner_id = auth.uid());

drop policy if exists "workspaces_update_manager" on public.workspaces;
create policy "workspaces_update_manager"
  on public.workspaces
  for update
  to authenticated
  using (
    owner_id = auth.uid()
    or public.has_workspace_role(id, array['owner', 'editor']::public.workspace_role[])
  )
  with check (
    owner_id = auth.uid()
    or public.has_workspace_role(id, array['owner', 'editor']::public.workspace_role[])
  );

drop policy if exists "workspaces_delete_owner" on public.workspaces;
create policy "workspaces_delete_owner"
  on public.workspaces
  for delete
  to authenticated
  using (owner_id = auth.uid());

-- -------------------------------------------------------------------------
-- workspace_members
--   read:   own membership rows, or managers of that workspace
--   insert: managers (owner/editor) may add members for their workspace
--   update: managers only
--   delete: managers, but an owner row can only be removed by cascading
--           the workspace itself
-- -------------------------------------------------------------------------
drop policy if exists "workspace_members_select" on public.workspace_members;
create policy "workspace_members_select"
  on public.workspace_members
  for select
  to authenticated
  using (
    user_id = auth.uid()
    or public.has_workspace_role(workspace_id, array['owner', 'editor']::public.workspace_role[])
  );

drop policy if exists "workspace_members_insert_manager" on public.workspace_members;
create policy "workspace_members_insert_manager"
  on public.workspace_members
  for insert
  to authenticated
  with check (
    public.has_workspace_role(workspace_id, array['owner', 'editor']::public.workspace_role[])
  );

drop policy if exists "workspace_members_update_manager" on public.workspace_members;
create policy "workspace_members_update_manager"
  on public.workspace_members
  for update
  to authenticated
  using (
    public.has_workspace_role(workspace_id, array['owner', 'editor']::public.workspace_role[])
  )
  with check (
    public.has_workspace_role(workspace_id, array['owner', 'editor']::public.workspace_role[])
  );

drop policy if exists "workspace_members_delete_manager" on public.workspace_members;
create policy "workspace_members_delete_manager"
  on public.workspace_members
  for delete
  to authenticated
  using (
    role <> 'owner'
    and public.has_workspace_role(
      workspace_id,
      array['owner', 'editor']::public.workspace_role[]
    )
  );

-- -------------------------------------------------------------------------
-- user_preferences
--   read/write: the owning user only
-- -------------------------------------------------------------------------
drop policy if exists "user_preferences_select_self" on public.user_preferences;
create policy "user_preferences_select_self"
  on public.user_preferences
  for select
  to authenticated
  using (user_id = auth.uid());

drop policy if exists "user_preferences_insert_self" on public.user_preferences;
create policy "user_preferences_insert_self"
  on public.user_preferences
  for insert
  to authenticated
  with check (user_id = auth.uid());

drop policy if exists "user_preferences_update_self" on public.user_preferences;
create policy "user_preferences_update_self"
  on public.user_preferences
  for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- -------------------------------------------------------------------------
-- Explicit note on privileged access:
--   service_role bypasses RLS. It is used only by trusted server code
--   (backend services, migrations) and must never be exposed to browsers.
--   No policy in this file grants anything to anon.
-- -------------------------------------------------------------------------
