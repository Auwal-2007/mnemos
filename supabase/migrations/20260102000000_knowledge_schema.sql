-- =========================================================================
-- MNEMOS — Phase 2A knowledge schema (provenance-aware)
--
-- Model
--   sources            — a user's submitted item (uploaded document or note)
--   document_versions  — every submission of a source; never overwritten
--   extracted_contents — text derived from a version (distinct from original)
--   extracted_pages    — character offsets per PDF page / text segment
--   chunks             — deterministic retrieval units of a version
--   provenance_records — the stable citation identity for a chunk
--
-- Invariants enforced in this file
--   * a chunk always belongs to the same workspace and source as its version
--     (composite FK + validating trigger)
--   * a provenance record always points at the chunk's own source/version
--   * exactly one current version per source (partial unique index)
--   * content hashes are lowercase sha256 hex
--   * timestamps are explicit: created_at (row), submitted_at (user action)
--
-- Deliberately NOT created here: embeddings, conversations, answers, claims,
-- verification records, revisions, conflicts. Those arrive in 2C, 3B, 3C, 4A.
--
-- Idempotent: safe to re-run.
-- =========================================================================

-- -------------------------------------------------------------------------
-- Enumerations
-- -------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'source_kind') then
    create type public.source_kind as enum ('document', 'note');
  end if;
  if not exists (select 1 from pg_type where typname = 'processing_status') then
    create type public.processing_status as enum (
      'pending', 'validating', 'extracting', 'extracted',
      'chunking', 'indexing', 'ready', 'failed'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'extraction_status') then
    create type public.extraction_status as enum (
      'pending', 'extracting', 'extracted', 'failed'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'embedding_status') then
    create type public.embedding_status as enum ('pending', 'embedded', 'failed');
  end if;
  if not exists (select 1 from pg_type where typname = 'information_status') then
    -- The *epistemic* status of a piece of stored information. It is not the
    -- same thing as a document's processing status.
    create type public.information_status as enum (
      'current', 'superseded', 'disputed', 'archived', 'pending_review'
    );
  end if;
end;
$$;

-- -------------------------------------------------------------------------
-- Shared hash validation helper
-- -------------------------------------------------------------------------
create or replace function public.is_sha256_hex(value text)
returns boolean
language sql
immutable
as $$
  select value ~ '^[0-9a-f]{64}$';
$$;

comment on function public.is_sha256_hex(text) is
  'True for lowercase sha256 hex digests. Used by content_hash checks.';

-- -------------------------------------------------------------------------
-- sources — one row per submitted item
-- -------------------------------------------------------------------------
create table if not exists public.sources (
  id                       uuid primary key default gen_random_uuid(),
  workspace_id             uuid not null references public.workspaces (id) on delete cascade,
  owner_id                 uuid not null references auth.users (id) on delete cascade,
  kind                     public.source_kind not null,
  title                    text not null check (char_length(trim(title)) between 1 and 300),
  original_filename        text check (
                             original_filename is null
                             or char_length(original_filename) between 1 and 255
                           ),
  mime_type                text not null check (char_length(mime_type) between 3 and 255),
  size_bytes               bigint not null check (size_bytes >= 0 and size_bytes <= 52428800),
  content_hash             text not null check (public.is_sha256_hex(content_hash)),
  storage_bucket           text not null default 'sources',
  storage_path             text not null check (char_length(storage_path) between 1 and 1024),
  processing_status        public.processing_status not null default 'pending',
  processing_error_code    text check (processing_error_code is null or char_length(processing_error_code) <= 64),
  processing_error_detail  text check (processing_error_detail is null or char_length(processing_error_detail) <= 500),
  processing_attempts      integer not null default 0 check (processing_attempts >= 0),
  idempotency_key          text check (idempotency_key is null or char_length(idempotency_key) between 8 and 128),
  metadata                 jsonb not null default '{}'::jsonb,
  submitted_at             timestamptz not null default now(),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  -- Composite key so children can prove they share the workspace.
  constraint sources_id_workspace_unique unique (id, workspace_id),
  -- A note has no client filename; a document must have one.
  constraint sources_kind_filename_consistent check (
    (kind = 'note' and original_filename is null)
    or (kind = 'document' and original_filename is not null)
  )
);

comment on table public.sources is
  'A submitted item. The row is a container; its content lives in document_versions. Deleting a source removes all derived data.';
comment on column public.sources.owner_id is
  'The user who submitted the item. Must hold editor/owner role in the workspace.';
comment on column public.sources.content_hash is
  'sha256 of the submitted bytes. Identical bytes may legitimately exist as separate sources.';
comment on column public.sources.idempotency_key is
  'Client-supplied key preventing duplicate source creation on retry. Unique per workspace.';
comment on column public.sources.processing_status is
  'Coarse pipeline position. The authoritative per-version detail lives in document_versions.';

create index if not exists sources_workspace_created_idx
  on public.sources (workspace_id, created_at desc);
create index if not exists sources_owner_idx on public.sources (owner_id);
create index if not exists sources_status_idx on public.sources (processing_status);
create unique index if not exists sources_idempotency_unique_idx
  on public.sources (workspace_id, idempotency_key)
  where idempotency_key is not null;

drop trigger if exists sources_set_updated_at on public.sources;
create trigger sources_set_updated_at
  before update on public.sources
  for each row execute function public.set_updated_at();

-- -------------------------------------------------------------------------
-- document_versions — every submission; never overwritten in place
-- -------------------------------------------------------------------------
create table if not exists public.document_versions (
  id                       uuid primary key default gen_random_uuid(),
  workspace_id             uuid not null,
  source_id                uuid not null,
  version_number           integer not null check (version_number >= 1),
  content_hash             text not null check (public.is_sha256_hex(content_hash)),
  size_bytes               bigint not null check (size_bytes >= 0 and size_bytes <= 52428800),
  mime_type                text not null,
  storage_bucket           text not null default 'sources',
  storage_path             text not null check (char_length(storage_path) between 1 and 1024),
  extraction_status        public.extraction_status not null default 'pending',
  extraction_method        text check (extraction_method is null or char_length(extraction_method) <= 64),
  extraction_error_code    text check (extraction_error_code is null or char_length(extraction_error_code) <= 64),
  extraction_error_detail  text check (extraction_error_detail is null or char_length(extraction_error_detail) <= 500),
  extracted_at             timestamptz,
  indexing_config          jsonb not null default '{}'::jsonb,
  is_current               boolean not null default true,
  idempotency_key          text check (idempotency_key is null or char_length(idempotency_key) between 8 and 128),
  submitted_by             uuid references auth.users (id) on delete set null,
  submitted_at             timestamptz not null default now(),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  constraint document_versions_id_workspace_unique unique (id, workspace_id),
  constraint document_versions_source_version_unique unique (source_id, version_number),
  constraint document_versions_source_workspace_fk
    foreign key (source_id, workspace_id)
    references public.sources (id, workspace_id) on delete cascade
);

comment on table public.document_versions is
  'Immutable submission record. A new submission creates a new version; the previous version is retained and marked is_current=false.';
comment on column public.document_versions.is_current is
  'Latest submitted version of this source. Says nothing about whether the information inside is still true.';

create index if not exists document_versions_source_idx
  on public.document_versions (source_id, version_number desc);
create index if not exists document_versions_workspace_idx
  on public.document_versions (workspace_id);
-- Exactly one current version per source.
create unique index if not exists document_versions_one_current_idx
  on public.document_versions (source_id)
  where is_current;
create unique index if not exists document_versions_idempotency_unique_idx
  on public.document_versions (source_id, idempotency_key)
  where idempotency_key is not null;

drop trigger if exists document_versions_set_updated_at on public.document_versions;
create trigger document_versions_set_updated_at
  before update on public.document_versions
  for each row execute function public.set_updated_at();

-- Assign monotonically increasing version numbers. The unique constraint is
-- the authoritative guard; concurrent inserts surface a constraint error and
-- the service retries once (documented in INGESTION_PIPELINE.md).
create or replace function public.assign_version_number()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.version_number is null or new.version_number < 1 then
    select coalesce(max(version_number), 0) + 1
      into new.version_number
      from public.document_versions
     where source_id = new.source_id;
  end if;
  return new;
end;
$$;

drop trigger if exists document_versions_assign_number on public.document_versions;
create trigger document_versions_assign_number
  before insert on public.document_versions
  for each row execute function public.assign_version_number();

-- -------------------------------------------------------------------------
-- extracted_contents — derived text, kept separate from the original file
-- -------------------------------------------------------------------------
create table if not exists public.extracted_contents (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null,
  document_version_id uuid not null,
  content             text not null check (char_length(content) >= 0),
  content_hash        text not null check (public.is_sha256_hex(content_hash)),
  char_count          integer not null check (char_count >= 0),
  extraction_method   text not null check (char_length(extraction_method) between 1 and 64),
  page_count          integer not null default 0 check (page_count >= 0),
  metadata            jsonb not null default '{}'::jsonb,
  created_at          timestamptz not null default now(),
  constraint extracted_contents_version_unique unique (document_version_id),
  constraint extracted_contents_version_workspace_fk
    foreign key (document_version_id, workspace_id)
    references public.document_versions (id, workspace_id) on delete cascade,
  constraint extracted_contents_char_count_matches check (char_count = char_length(content))
);

comment on table public.extracted_contents is
  'Plain text derived from a version. Never the source of truth: the original bytes stay in private storage.';

create index if not exists extracted_contents_workspace_idx
  on public.extracted_contents (workspace_id);

-- -------------------------------------------------------------------------
-- extracted_pages — offsets so a citation can point at a real location
-- -------------------------------------------------------------------------
create table if not exists public.extracted_pages (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null,
  document_version_id uuid not null,
  page_number         integer not null check (page_number >= 1),
  start_offset        integer not null check (start_offset >= 0),
  end_offset          integer not null check (end_offset >= start_offset),
  constraint extracted_pages_version_page_unique unique (document_version_id, page_number),
  constraint extracted_pages_version_workspace_fk
    foreign key (document_version_id, workspace_id)
    references public.document_versions (id, workspace_id) on delete cascade
);

comment on table public.extracted_pages is
  'Half-open character range [start_offset, end_offset) of extracted_contents.content for each page or segment. Preserves location for PDFs and multi-part text.';

create index if not exists extracted_pages_version_idx
  on public.extracted_pages (document_version_id, page_number);

-- -------------------------------------------------------------------------
-- chunks — deterministic retrieval units
-- -------------------------------------------------------------------------
create table if not exists public.chunks (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null,
  source_id           uuid not null,
  document_version_id uuid not null,
  chunk_index         integer not null check (chunk_index >= 0),
  content             text not null check (char_length(content) > 0),
  content_hash        text not null check (public.is_sha256_hex(content_hash)),
  char_count          integer not null check (char_count > 0),
  source_location     jsonb not null,
  chunking_method     text not null check (char_length(chunking_method) between 1 and 64),
  chunking_version    integer not null check (chunking_version >= 1),
  embedding_status    public.embedding_status not null default 'pending',
  metadata            jsonb not null default '{}'::jsonb,
  created_at          timestamptz not null default now(),
  constraint chunks_version_index_unique unique (document_version_id, chunk_index),
  constraint chunks_version_workspace_fk
    foreign key (document_version_id, workspace_id)
    references public.document_versions (id, workspace_id) on delete cascade,
  constraint chunks_source_workspace_fk
    foreign key (source_id, workspace_id)
    references public.sources (id, workspace_id) on delete cascade,
  constraint chunks_char_count_matches check (char_count = char_length(content)),
  constraint chunks_location_offsets_present check (
    source_location ? 'start_offset' and source_location ? 'end_offset'
  ),
  constraint chunks_location_offsets_valid check (
    (source_location ->> 'start_offset')::integer >= 0
    and (source_location ->> 'end_offset')::integer
        >= (source_location ->> 'start_offset')::integer
  )
);

comment on table public.chunks is
  'A deterministic slice of a version. source_location always carries character offsets and a page number when the original had pages.';
comment on column public.chunks.content_hash is
  'sha256 of content. Detects silent content drift and lets re-indexing skip unchanged text.';

create index if not exists chunks_version_idx on public.chunks (document_version_id, chunk_index);
create index if not exists chunks_source_idx on public.chunks (source_id);
create index if not exists chunks_workspace_idx on public.chunks (workspace_id);

-- A chunk may not claim a source that is not its version's source.
create or replace function public.validate_chunk_relationships()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  version_source uuid;
begin
  select source_id into version_source
    from public.document_versions
   where id = new.document_version_id;

  if version_source is null then
    raise exception 'chunk references unknown document_version %', new.document_version_id
      using errcode = 'foreign_key_violation';
  end if;

  if version_source <> new.source_id then
    raise exception
      'chunk source_id % does not match document_version source_id %',
      new.source_id, version_source
      using errcode = 'integrity_constraint_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists chunks_validate_relationships on public.chunks;
create trigger chunks_validate_relationships
  before insert or update of source_id, document_version_id on public.chunks
  for each row execute function public.validate_chunk_relationships();

-- -------------------------------------------------------------------------
-- provenance_records — the stable citation identity for a chunk
-- -------------------------------------------------------------------------
create table if not exists public.provenance_records (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null,
  source_id           uuid not null,
  document_version_id uuid not null,
  chunk_id            uuid not null unique,
  source_location     jsonb not null,
  information_status  public.information_status not null default 'current',
  revision_of         uuid references public.provenance_records (id) on delete set null,
  superseded_by       uuid references public.provenance_records (id) on delete set null,
  resolution_metadata jsonb not null default '{}'::jsonb,
  submitted_at        timestamptz not null,
  created_at          timestamptz not null default now(),
  constraint provenance_chunk_fk
    foreign key (chunk_id) references public.chunks (id) on delete cascade,
  constraint provenance_version_workspace_fk
    foreign key (document_version_id, workspace_id)
    references public.document_versions (id, workspace_id) on delete cascade,
  constraint provenance_chunk_location_present check (
    source_location ? 'start_offset' and source_location ? 'end_offset'
  ),
  constraint provenance_not_self_superseding check (superseded_by is null or superseded_by <> id),
  constraint provenance_not_self_revision check (revision_of is null or revision_of <> id)
);

comment on table public.provenance_records is
  'One row per chunk: the durable citation identity (provenance_id) used by evidence, answers, claims and verification. Never rewritten; information_status changes are recorded separately.';
comment on column public.provenance_records.information_status is
  'Epistemic status of the passage. Superseded material stays queryable for historical questions.';

create index if not exists provenance_workspace_status_idx
  on public.provenance_records (workspace_id, information_status);
create index if not exists provenance_source_idx on public.provenance_records (source_id);
create index if not exists provenance_version_idx on public.provenance_records (document_version_id);

create or replace function public.validate_provenance_relationships()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  chunk_source uuid;
  chunk_version uuid;
  chunk_location jsonb;
  version_submitted timestamptz;
begin
  select source_id, document_version_id, source_location
    into chunk_source, chunk_version, chunk_location
    from public.chunks
   where id = new.chunk_id;

  if chunk_version is null then
    raise exception 'provenance references unknown chunk %', new.chunk_id
      using errcode = 'foreign_key_violation';
  end if;

  if chunk_version <> new.document_version_id or chunk_source <> new.source_id then
    raise exception
      'provenance source/version must match the chunk (chunk=%/%)',
      chunk_source, chunk_version
      using errcode = 'integrity_constraint_violation';
  end if;

  if new.source_location <> chunk_location then
    raise exception 'provenance source_location must match the chunk location'
      using errcode = 'integrity_constraint_violation';
  end if;

  select submitted_at into version_submitted
    from public.document_versions
   where id = new.document_version_id;

  if new.submitted_at <> version_submitted then
    raise exception 'provenance submitted_at must equal the version submitted_at'
      using errcode = 'integrity_constraint_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists provenance_validate_relationships on public.provenance_records;
create trigger provenance_validate_relationships
  before insert or update of chunk_id, source_id, document_version_id, source_location, submitted_at
  on public.provenance_records
  for each row execute function public.validate_provenance_relationships();

-- -------------------------------------------------------------------------
-- Resolution: one function that returns the reusable provenance contract.
-- SECURITY INVOKER, so the caller's RLS policies still apply.
-- -------------------------------------------------------------------------
create or replace function public.resolve_chunk_provenance(p_chunk_id uuid)
returns table (
  provenance_id        uuid,
  chunk_id             uuid,
  source_id            uuid,
  document_version_id  uuid,
  workspace_id         uuid,
  source_title         text,
  source_kind          public.source_kind,
  version_number       integer,
  source_location      jsonb,
  chunk_index          integer,
  information_status   public.information_status,
  revision_reference   uuid,
  superseded_by        uuid,
  document_created_at  timestamptz,
  submitted_at         timestamptz,
  resolution_metadata  jsonb
)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select
    p.id,
    c.id,
    s.id,
    v.id,
    s.workspace_id,
    s.title,
    s.kind,
    v.version_number,
    p.source_location,
    c.chunk_index,
    p.information_status,
    p.revision_of,
    p.superseded_by,
    v.created_at,
    p.submitted_at,
    p.resolution_metadata
  from public.provenance_records p
  join public.chunks c on c.id = p.chunk_id
  join public.document_versions v on v.id = p.document_version_id
  join public.sources s on s.id = p.source_id
  where p.chunk_id = p_chunk_id;
$$;

comment on function public.resolve_chunk_provenance(uuid) is
  'Resolves a chunk to the full provenance contract. SECURITY INVOKER: RLS on the underlying tables applies to the caller.';
