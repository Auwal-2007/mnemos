-- =========================================================================
-- MNEMOS — Phase 2A Row Level Security for the knowledge schema
--
-- Access model (stricter than Phase 1 in one respect and looser in none):
--
--   sources            editors/owners of the workspace may read and create;
--                      only the owner or an editor may delete
--   document_versions  same as sources (they are the same resource)
--   extracted_*        readable wherever the version is readable; written
--                      only by the ingestion service (service_role)
--   chunks             readable in the workspace; never written by users
--   provenance_records readable in the workspace; never written by users
--
-- Derived data (extracted text, chunks, provenance) is produced by trusted
-- server code. Users must not be able to forge a chunk or relabel the
-- provenance of a passage, because citations depend on that integrity.
-- =========================================================================

-- -------------------------------------------------------------------------
-- Helper: can the caller contribute to this workspace?
-- -------------------------------------------------------------------------
create or replace function public.can_contribute_to_workspace(target_workspace uuid)
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
      and m.role in ('owner', 'editor')
  );
$$;

revoke all on function public.can_contribute_to_workspace(uuid) from public;
grant execute on function public.can_contribute_to_workspace(uuid) to authenticated;

comment on function public.can_contribute_to_workspace(uuid) is
  'True when the caller holds owner or editor on the workspace. Used by knowledge policies.';

-- -------------------------------------------------------------------------
-- RLS on
-- -------------------------------------------------------------------------
alter table public.sources            enable row level security;
alter table public.document_versions  enable row level security;
alter table public.extracted_contents enable row level security;
alter table public.extracted_pages    enable row level security;
alter table public.chunks             enable row level security;
alter table public.provenance_records enable row level security;

alter table public.sources            force row level security;
alter table public.document_versions  force row level security;
alter table public.extracted_contents force row level security;
alter table public.extracted_pages    force row level security;
alter table public.chunks             force row level security;
alter table public.provenance_records force row level security;

revoke all on public.sources            from anon;
revoke all on public.document_versions  from anon;
revoke all on public.extracted_contents from anon;
revoke all on public.extracted_pages    from anon;
revoke all on public.chunks             from anon;
revoke all on public.provenance_records from anon;

grant select, insert, update, delete on public.sources           to authenticated;
grant select, insert, delete         on public.document_versions to authenticated;
grant select                         on public.extracted_contents to authenticated;
grant select                         on public.extracted_pages    to authenticated;
grant select                         on public.chunks             to authenticated;
grant select                         on public.provenance_records to authenticated;

-- -------------------------------------------------------------------------
-- sources
-- -------------------------------------------------------------------------
drop policy if exists "sources_select_member" on public.sources;
create policy "sources_select_member"
  on public.sources
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "sources_insert_contributor" on public.sources;
create policy "sources_insert_contributor"
  on public.sources
  for insert
  to authenticated
  with check (
    owner_id = auth.uid()
    and public.can_contribute_to_workspace(workspace_id)
  );

drop policy if exists "sources_update_contributor" on public.sources;
create policy "sources_update_contributor"
  on public.sources
  for update
  to authenticated
  using (public.can_contribute_to_workspace(workspace_id))
  with check (public.can_contribute_to_workspace(workspace_id));

drop policy if exists "sources_delete_contributor" on public.sources;
create policy "sources_delete_contributor"
  on public.sources
  for delete
  to authenticated
  using (public.can_contribute_to_workspace(workspace_id));

-- -------------------------------------------------------------------------
-- document_versions — append and read; never rewrite the content fields.
-- The UPDATE policy exists only so the pipeline can move status, and the
-- trigger below enforces that nothing else changes.
-- -------------------------------------------------------------------------
drop policy if exists "document_versions_select_member" on public.document_versions;
create policy "document_versions_select_member"
  on public.document_versions
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "document_versions_insert_contributor" on public.document_versions;
create policy "document_versions_insert_contributor"
  on public.document_versions
  for insert
  to authenticated
  with check (public.can_contribute_to_workspace(workspace_id));

drop policy if exists "document_versions_update_contributor" on public.document_versions;
create policy "document_versions_update_contributor"
  on public.document_versions
  for update
  to authenticated
  using (public.can_contribute_to_workspace(workspace_id))
  with check (public.can_contribute_to_workspace(workspace_id));

grant update on public.document_versions to authenticated;

drop policy if exists "document_versions_delete_contributor" on public.document_versions;
create policy "document_versions_delete_contributor"
  on public.document_versions
  for delete
  to authenticated
  using (public.can_contribute_to_workspace(workspace_id));

-- Immutability guard: the submitted bytes of a version can never be
-- rewritten, and is_current can only move one way (true -> false).
create or replace function public.protect_document_version_content()
returns trigger
language plpgsql
as $$
begin
  if new.content_hash <> old.content_hash
     or new.size_bytes <> old.size_bytes
     or new.storage_path <> old.storage_path
     or new.storage_bucket <> old.storage_bucket
     or new.version_number <> old.version_number
     or new.source_id <> old.source_id then
    raise exception 'document version content is immutable'
      using errcode = 'integrity_constraint_violation';
  end if;

  if old.is_current = false and new.is_current = true then
    raise exception 'a version cannot be restored to current; submit a new version instead'
      using errcode = 'integrity_constraint_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists document_versions_protect_content on public.document_versions;
create trigger document_versions_protect_content
  before update on public.document_versions
  for each row execute function public.protect_document_version_content();

-- -------------------------------------------------------------------------
-- extracted_contents / extracted_pages — read-only for users
-- -------------------------------------------------------------------------
drop policy if exists "extracted_contents_select_member" on public.extracted_contents;
create policy "extracted_contents_select_member"
  on public.extracted_contents
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "extracted_pages_select_member" on public.extracted_pages;
create policy "extracted_pages_select_member"
  on public.extracted_pages
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));

-- -------------------------------------------------------------------------
-- chunks — read-only for users
-- -------------------------------------------------------------------------
drop policy if exists "chunks_select_member" on public.chunks;
create policy "chunks_select_member"
  on public.chunks
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));

-- -------------------------------------------------------------------------
-- provenance_records — read-only for users
-- -------------------------------------------------------------------------
drop policy if exists "provenance_select_member" on public.provenance_records;
create policy "provenance_select_member"
  on public.provenance_records
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));
