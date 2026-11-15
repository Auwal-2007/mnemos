-- =========================================================================
-- MNEMOS — Phase 2C chunk embeddings (pgvector)
--
-- Verified locally before this migration was written:
--   * pgvector 0.6.2 is available and HNSW index creation works
--   * a `vector(N)` column rejects a vector of any other length
--     ("expected 3 dimensions, not 2"), which is the guarantee this schema
--     relies on to prevent mixed-dimensional indexes
--
-- Dimension
--   The column dimension is NOT hardcoded into application logic: it comes from
--   the `app.embedding_dimension` setting, supplied by the migration runner.
--   The default here (1536) matches `EMBEDDING_DIMENSION`'s default and is only
--   used when the setting is absent. Changing it requires a new migration and a
--   full re-index — deliberately, because silently mixing dimensions in one
--   column would make every distance comparison meaningless.
--
--   Because SQL cannot parameterise a type modifier, the migration reads the
--   value from a session setting and builds the DDL with format(). The value is
--   validated as an integer between 1 and 16000 (pgvector's HNSW ceiling is
--   2000 for `vector`; the common embedding models are 384–3072).
--
-- Isolation
--   Embeddings live beside chunks with the same workspace column, so RLS and
--   every ownership invariant apply unchanged. There is no separate vector
--   store to keep consistent.
--
-- Idempotent, and safe to re-run.
-- =========================================================================

-- -------------------------------------------------------------------------
-- pgvector availability check — fail loudly, never skip silently
-- -------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_available_extensions where name = 'vector') then
    raise exception
      'pgvector is not available on this server. Enable the vector extension '
      'before applying this migration (Supabase: Database > Extensions).'
      using errcode = 'feature_not_supported';
  end if;
end;
$$;

create extension if not exists vector;

-- -------------------------------------------------------------------------
-- Resolve and validate the configured dimension
-- -------------------------------------------------------------------------
do $$
declare
  configured text := coalesce(current_setting('app.embedding_dimension', true), '');
  dimension integer;
begin
  if configured = '' then
    dimension := 1536;
  else
    if configured !~ '^[0-9]+$' then
      raise exception 'app.embedding_dimension must be an integer, got %', configured
        using errcode = 'invalid_parameter_value';
    end if;
    dimension := configured::integer;
  end if;

  if dimension < 1 or dimension > 16000 then
    raise exception 'app.embedding_dimension % is outside the supported range 1..16000', dimension
      using errcode = 'invalid_parameter_value';
  end if;

  perform set_config('mnemos.embedding_dimension', dimension::text, false);
end;
$$;

-- -------------------------------------------------------------------------
-- chunk_embeddings
--   One vector per chunk. The model id and dimension are stored per row so a
--   future model change can be audited rather than inferred.
-- -------------------------------------------------------------------------
do $$
declare
  dimension integer := current_setting('mnemos.embedding_dimension')::integer;
  ddl text;
begin
  if not exists (select 1 from pg_tables where schemaname = 'public' and tablename = 'chunk_embeddings') then
    ddl := format($f$
      create table public.chunk_embeddings (
        chunk_id        uuid primary key references public.chunks (id) on delete cascade,
        workspace_id    uuid not null,
        document_version_id uuid not null,
        embedding_model text not null check (char_length(embedding_model) between 1 and 128),
        embedding_dim   integer not null check (embedding_dim = %1$s),
        embedding       vector(%1$s) not null,
        created_at      timestamptz not null default now(),
        constraint chunk_embeddings_chunk_workspace_fk
          foreign key (document_version_id, workspace_id)
          references public.document_versions (id, workspace_id) on delete cascade
      );
    $f$, dimension);
    execute ddl;
  end if;

  -- If the table already exists with a different dimension, refuse rather than
  -- silently keeping a mismatched column.
  if exists (
    select 1 from information_schema.columns
     where table_schema = 'public'
       and table_name = 'chunk_embeddings'
       and column_name = 'embedding_dim'
  ) then
    if not exists (
      select 1 from pg_constraint
       where conname = 'chunk_embeddings_dimension_guard'
    ) then
      execute format(
        'alter table public.chunk_embeddings add constraint chunk_embeddings_dimension_guard
           check (embedding_dim = %s)', dimension);
    end if;
  end if;
end;
$$;

comment on table public.chunk_embeddings is
  'One embedding vector per chunk. Dimension is fixed at migration time; mixing dimensions in one column would make distance comparisons meaningless.';
comment on column public.chunk_embeddings.embedding_model is
  'The exact model id that produced the vector, recorded per row so a model change is auditable.';

-- Vector index. Cosine distance because embedding models are trained for
-- cosine similarity and the vectors are not normalised by every provider.
-- HNSW over IVFFlat: no training pass, better recall at small corpus sizes,
-- and insertion-time cost is acceptable for a personal knowledge system.
do $$
begin
  if not exists (
    select 1 from pg_class where relname = 'chunk_embeddings_hnsw_idx'
  ) then
    execute 'create index chunk_embeddings_hnsw_idx
               on public.chunk_embeddings
               using hnsw (embedding vector_cosine_ops)
               with (m = 16, ef_construction = 64)';
  end if;
end;
$$;

create index if not exists chunk_embeddings_workspace_idx
  on public.chunk_embeddings (workspace_id);
create index if not exists chunk_embeddings_version_idx
  on public.chunk_embeddings (document_version_id);

-- -------------------------------------------------------------------------
-- Row Level Security: embeddings are as sensitive as the text they encode
-- -------------------------------------------------------------------------
alter table public.chunk_embeddings enable row level security;
alter table public.chunk_embeddings force row level security;

revoke all on public.chunk_embeddings from anon;
grant select on public.chunk_embeddings to authenticated;

drop policy if exists "chunk_embeddings_select_member" on public.chunk_embeddings;
create policy "chunk_embeddings_select_member"
  on public.chunk_embeddings
  for select
  to authenticated
  using (public.is_workspace_member(workspace_id));

-- -------------------------------------------------------------------------
-- Cosine similarity search, scoped by RLS at the caller's identity.
-- SECURITY INVOKER: a caller outside the workspace gets no rows.
-- -------------------------------------------------------------------------
create or replace function public.match_chunks(
  p_workspace_id uuid,
  p_query_embedding vector,
  p_match_count integer default 10,
  p_min_similarity double precision default 0.0
)
returns table (
  chunk_id uuid,
  similarity double precision,
  embedding_model text
)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select
    e.chunk_id,
    1 - (e.embedding <=> p_query_embedding) as similarity,
    e.embedding_model
  from public.chunk_embeddings e
  where e.workspace_id = p_workspace_id
    and 1 - (e.embedding <=> p_query_embedding) >= p_min_similarity
  order by e.embedding <=> p_query_embedding
  limit least(coalesce(p_match_count, 10), 100);
$$;

comment on function public.match_chunks(uuid, vector, integer, double precision) is
  'Cosine similarity search over one workspace. SECURITY INVOKER so RLS applies; the embedding dimension must match the column or PostgreSQL raises.';
