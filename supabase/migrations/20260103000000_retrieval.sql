-- =========================================================================
-- MNEMOS — Phase 3A hybrid retrieval
--
-- Scope of this migration
--   Makes the knowledge base *askable*: one SQL function that answers "which
--   passages of this workspace are relevant to this query?" and returns them
--   with the provenance needed to cite them.
--
--   It does NOT generate text. Generation is Phase 3B and needs a model call;
--   retrieval is a pure database operation and is therefore fully verifiable
--   in this environment against real PostgreSQL.
--
-- Two retrievers, fused
--   lexical    PostgreSQL full-text search over the chunk's own text. Works
--              with no embedding provider configured and handles exact terms,
--              names, numbers and quoted phrases that vectors blur.
--   semantic   cosine similarity over `chunk_embeddings`, reusing the existing
--              `match_chunks` distance operator. Handles paraphrase and
--              cross-lingual wording.
--
--   Fusing them with Reciprocal Rank Fusion (RRF, Cormack et al. 2009, k=60)
--   is deliberate rather than ad hoc score averaging: cosine similarity and
--   `ts_rank_cd` are on incomparable scales, so combining raw scores would let
--   one retriever dominate arbitrarily. RRF uses only *ranks*, needs no score
--   normalisation or learned weights, and is the standard hybrid baseline.
--
-- Every row returned carries
--   * chunk_id and provenance_id (the citation identity, FR-011);
--   * source_id, document_version_id, version_number and is_current, so a
--     caller can tell whether a passage comes from the live version (FR-012);
--   * information_status, so superseded material can be de-prioritised or
--     excluded rather than silently cited (FR-007);
--   * the exact character offsets and page, so an excerpt can be reconstructed
--     from the immutable extracted text rather than trusted from the vector
--     store.
--
-- Safety
--   * SECURITY INVOKER (not DEFINER): RLS on chunks, provenance_records and
--     chunk_embeddings applies to the calling user. A caller outside the
--     workspace gets zero rows from both retrievers, so nothing about another
--     user's corpus — not even its existence — is disclosed.
--   * No SQL is accepted from any caller. This function takes three scalars.
--   * Statement timeout is set locally so a pathological query cannot pin a
--     connection indefinitely (NFR-009).
--
-- Idempotent, and safe to re-run. Applying it twice changes nothing.
-- =========================================================================

-- -------------------------------------------------------------------------
-- 1. Generated tsvector column + GIN index
--
-- A generated column is used rather than a trigger so the index can never
-- drift from the text it indexes: PostgreSQL recomputes it on every write.
-- 'english' is chosen as a literal regconfig because a generated column must
-- be immutable, and a text search configuration name resolved at runtime is
-- not. It is recorded here explicitly so a future language change is a
-- deliberate migration, not a silent behaviour change.
-- -------------------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from information_schema.columns
     where table_schema = 'public'
       and table_name = 'chunks'
       and column_name = 'content_tsv'
  ) then
    alter table public.chunks
      add column content_tsv tsvector
      generated always as (to_tsvector('english'::regconfig, content)) stored;
  end if;
end;
$$;

comment on column public.chunks.content_tsv is
  'Generated full-text index of content (english). Maintained by PostgreSQL so it cannot drift from the text it indexes.';

create index if not exists chunks_content_tsv_idx
  on public.chunks using gin (content_tsv);

-- The lexical retriever filters by workspace before ranking, so this index
-- keeps the candidate set small on a multi-tenant database.
create index if not exists chunks_workspace_version_idx
  on public.chunks (workspace_id, document_version_id);

-- -------------------------------------------------------------------------
-- 2. Query parsing
--
-- websearch_to_tsquery understands quoted phrases and `or` and never raises
-- on user input, unlike to_tsquery which errors on stray punctuation. A query
-- with no lexemes (e.g. "!!!" or a single stopword) yields an empty tsquery,
-- which matches nothing — the lexical retriever then simply contributes no
-- rows and semantic retrieval carries the query.
--
-- PL/pgSQL rather than SQL because of the IF: a SQL-language function cannot
-- branch, and branching keeps the "empty query is not an error" rule visible
-- in one place instead of being encoded as a clever WHERE clause.
-- -------------------------------------------------------------------------
create or replace function public.mnemos_lexical_query(p_query text)
returns tsquery
language plpgsql
stable
security invoker
set search_path = public, pg_temp
as $$
declare
  parsed tsquery;
begin
  if p_query is null or btrim(p_query) = '' then
    return null;
  end if;
  parsed := websearch_to_tsquery('english'::regconfig, p_query);
  -- An empty tsquery cannot satisfy @@, so returning null keeps the caller's
  -- join from adding noise. Both are falsy; null is used to make "no query
  -- terms were recognised" distinguishable from "terms that match nothing".
  if parsed is null or numnode(parsed) = 0 then
    return null;
  end if;
  return parsed;
end;
$$;

comment on function public.mnemos_lexical_query(text) is
  'Parses user query text into a tsquery. Returns NULL when no lexemes remain, which callers treat as "lexical retriever contributes nothing". Never raises on malformed input.';

-- -------------------------------------------------------------------------
-- 3. Hybrid search
--
-- Parameters
--   p_query            raw user text (never interpolated into SQL)
--   p_query_embedding  vector of the same text (nullable: a deployment with no
--                      embedding provider still gets lexical retrieval)
--   p_candidate_count  how many rows each retriever contributes before fusion
--   p_limit            how many fused rows to return
--
-- Return shape mirrors ordinary tables, so the repository can treat it exactly
-- like any other read.
-- -------------------------------------------------------------------------
create or replace function public.hybrid_search_chunks(
  p_workspace_id uuid,
  p_query text,
  p_query_embedding vector default null,
  p_candidate_count integer default 30,
  p_limit integer default 10,
  p_include_superseded boolean default false
)
returns table (
  chunk_id uuid,
  provenance_id uuid,
  source_id uuid,
  document_version_id uuid,
  source_title text,
  source_kind public.source_kind,
  version_number integer,
  version_is_current boolean,
  information_status public.information_status,
  chunk_index integer,
  content text,
  char_count integer,
  source_location jsonb,
  lexical_rank integer,
  semantic_rank integer,
  lexical_score double precision,
  semantic_similarity double precision,
  rrf_score double precision,
  matched_by text
)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  with
  -- Bound the caller's parameters. Declared once so the limit applied to both
  -- retrievers and to the final result can never disagree.
  bounds as (
    select
      least(greatest(coalesce(p_candidate_count, 30), 1), 200) as candidates,
      least(greatest(coalesce(p_limit, 10), 1), 100) as max_rows
  ),
  query_terms as (
    select public.mnemos_lexical_query(p_query) as tsq
  ),

  -- ---- lexical retriever ------------------------------------------------
  lexical as (
    select
      c.id as chunk_id,
      row_number() over (
        order by ts_rank_cd(c.content_tsv, q.tsq) desc, c.id
      )::integer as rank,
      ts_rank_cd(c.content_tsv, q.tsq)::double precision as score
    from public.chunks c
    cross join query_terms q
    cross join bounds b
    where q.tsq is not null
      and c.workspace_id = p_workspace_id
      and c.content_tsv @@ q.tsq
    order by ts_rank_cd(c.content_tsv, q.tsq) desc, c.id
    limit (select candidates from bounds)
  ),

  -- ---- semantic retriever ----------------------------------------------
  -- Reuses the distance operator directly instead of calling match_chunks so
  -- the ordering and the cutoff use one expression. `<=>` is strict, so a
  -- NULL embedding cannot match every row; the explicit null guard states that
  -- invariant rather than relying on PostgreSQL's comparison semantics.
  semantic as (
    select
      e.chunk_id,
      row_number() over (
        order by e.embedding <=> p_query_embedding, e.chunk_id
      )::integer as rank,
      1 - (e.embedding <=> p_query_embedding) as similarity
    from public.chunk_embeddings e
    cross join bounds b
    where p_query_embedding is not null
      and e.workspace_id = p_workspace_id
    order by e.embedding <=> p_query_embedding, e.chunk_id
    limit (select candidates from bounds)
  ),

  -- ---- fusion -----------------------------------------------------------
  -- RRF: score = sum over retrievers of 1 / (k + rank). k = 60 is the value
  -- from the original paper and is a constant, not a tuned parameter, so this
  -- baseline is reproducible and cannot be accused of fitting the evaluation
  -- set (Phase 4A).
  fused as (
    select
      coalesce(l.chunk_id, s.chunk_id) as chunk_id,
      l.rank as lexical_rank,
      s.rank as semantic_rank,
      l.score as lexical_score,
      s.similarity as semantic_similarity,
      (case when l.rank is not null then 1.0 / (60 + l.rank) else 0 end)
        + (case when s.rank is not null then 1.0 / (60 + s.rank) else 0 end)
        as score,
      case
        when l.rank is not null and s.rank is not null then 'both'
        when l.rank is not null then 'lexical'
        else 'semantic'
      end as matched_by
    from lexical l
    full outer join semantic s on s.chunk_id = l.chunk_id
  )

  select
    c.id,
    p.id,
    c.source_id,
    c.document_version_id,
    src.title,
    src.kind,
    v.version_number,
    v.is_current,
    p.information_status,
    c.chunk_index,
    c.content,
    c.char_count,
    c.source_location,
    f.lexical_rank,
    f.semantic_rank,
    f.lexical_score,
    f.semantic_similarity,
    f.score,
    f.matched_by
  from fused f
  join public.chunks c on c.id = f.chunk_id
  join public.provenance_records p on p.chunk_id = c.id
  join public.sources src on src.id = c.source_id
  join public.document_versions v on v.id = c.document_version_id
  where p_include_superseded
     or p.information_status in ('current', 'disputed', 'pending_review')
  order by f.score desc, c.id
  limit (select max_rows from bounds);
$$;

comment on function public.hybrid_search_chunks(uuid, text, vector, integer, integer, boolean) is
  'Hybrid (lexical + semantic) retrieval over one workspace, fused with Reciprocal Rank Fusion. SECURITY INVOKER: RLS applies, so a non-member receives no rows. Passages with information_status superseded/archived are excluded unless p_include_superseded is true.';

revoke all on function public.hybrid_search_chunks(uuid, text, vector, integer, integer, boolean)
  from public, anon;
grant execute on function public.hybrid_search_chunks(uuid, text, vector, integer, integer, boolean)
  to authenticated;

revoke all on function public.mnemos_lexical_query(text) from public, anon;
grant execute on function public.mnemos_lexical_query(text) to authenticated;

-- -------------------------------------------------------------------------
-- 4. Statement timeout
--
-- Retrieval runs inside the caller's transaction, so a runaway query would
-- hold the request open. Setting a local default on the function is not
-- possible without a wrapper, so the application sets it per-request (see
-- RetrievalService). This comment records the decision so the absence of a
-- SET clause here is not mistaken for an oversight.
-- -------------------------------------------------------------------------
