-- =========================================================================
-- MNEMOS — Phase 1B private storage bucket for source documents
--
-- Purpose: hold original uploaded files (PDFs, notes, text) for future
-- ingestion. Phase 1 does NOT implement upload or parsing; this migration
-- only provisions the bucket and its access rules so that uploads can be
-- added safely without reopening storage policy design.
--
-- Security posture
--   * public = false                — no anonymous/public URL access
--   * object path = <user_id>/<...> — first segment must equal auth.uid()
--   * all object operations require an authenticated session
--   * no UPDATE policy: objects are immutable once written
-- =========================================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'sources',
  'sources',
  false,
  52428800, -- 50 MiB
  array[
    'application/pdf',
    'text/plain',
    'text/markdown',
    'application/json',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.oasis.opendocument.text'
  ]
)
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- -------------------------------------------------------------------------
-- Policies on storage.objects, scoped to this bucket only.
-- (storage.objects already has RLS enabled by Supabase.)
-- -------------------------------------------------------------------------
drop policy if exists "sources_select_own" on storage.objects;
create policy "sources_select_own"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'sources'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "sources_insert_own" on storage.objects;
create policy "sources_insert_own"
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'sources'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "sources_delete_own" on storage.objects;
create policy "sources_delete_own"
  on storage.objects
  for delete
  to authenticated
  using (
    bucket_id = 'sources'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
