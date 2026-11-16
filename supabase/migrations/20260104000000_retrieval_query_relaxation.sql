-- =============================================================================
-- Retrieval: query relaxation fallback
-- =============================================================================
--
-- Problem this fixes
-- ------------------
-- `websearch_to_tsquery` joins every recognised term with AND. A natural
-- question such as
--
--     "how long do visa applications currently take to process"
--
-- therefore requires all six lexemes to appear in one chunk before anything is
-- returned. On real questions this is close to never, and the measured effect
-- was severe: in the Phase 4A evaluation (22 cases, real PostgreSQL, real
-- migrations) **73.7% of answerable questions returned no evidence at all**.
--
-- Retrieval returning nothing is not a soft failure. The generation stage is
-- forbidden from answering without evidence (FR-010), so a whole-document
-- conjunction turns a recall problem into "the assistant refuses to answer".
--
-- Strategy
-- --------
-- Keep the strict query as the first attempt, because when it matches it is the
-- best signal available: every term is present. Only when it matches nothing in
-- the workspace do we fall back to the same lexemes joined with OR, letting
-- `ts_rank_cd` rank by term coverage. This is the standard keyword-retrieval
-- shape (OR the terms, rank by coverage) reached without discarding the
-- precision of an exact conjunction.
--
-- Why not relax unconditionally
-- -----------------------------
-- Always-OR admits single-common-word matches into the candidate pool. With a
-- small candidate budget those can displace genuinely relevant chunks. Trying
-- strict first costs one indexed existence probe and keeps the good case exact.
--
-- Why the fallback lives in SQL
-- -----------------------------
-- The tsquery is built here. Putting the decision anywhere else would mean two
-- callers could disagree about what "the query" is.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Relaxed query parsing
--
-- Rewrites the top-level conjunctions of the strict parse into disjunctions.
-- Phrase operators (`<->`) and explicit OR from `websearch_to_tsquery` survive
-- untouched: a caller who quoted a phrase still gets that phrase required.
-- ---------------------------------------------------------------------------
create or replace function public.mnemos_lexical_query_relaxed(p_query text)
returns tsquery
language plpgsql
stable
security invoker
set search_path = public, pg_temp
as $$
declare
  strict_q tsquery;
  relaxed_text text;
  relaxed_q tsquery;
begin
  strict_q := public.mnemos_lexical_query(p_query);
  if strict_q is null or numnode(strict_q) = 0 then
    return null;
  end if;

  -- A single lexeme has nothing to relax.
  if numnode(strict_q) = 1 then
    return strict_q;
  end if;

  relaxed_text := replace(strict_q::text, '&', '|');
  if relaxed_text = strict_q::text then
    -- The query already used disjunctions (or phrases only); it is as relaxed
    -- as it can be.
    return strict_q;
  end if;

  begin
    relaxed_q := relaxed_text::tsquery;
  exception
    when others then
      -- Never raise on user input: fall back to the strict parse, which is
      -- still a valid query.
      return strict_q;
  end;
  if relaxed_q is null or numnode(relaxed_q) = 0 then
    return strict_q;
  end if;
  return relaxed_q;
end;
$$;

comment on function public.mnemos_lexical_query_relaxed(text) is
  'Parses query text into an OR-joined tsquery for use only as a fallback when the strict conjunction matches nothing. Preserves explicit phrases and OR groups. Never raises.';

-- ---------------------------------------------------------------------------
-- Hybrid search, with strict-then-relaxed lexical matching
--
-- Identical to the previous definition except for `query_terms`, which now
-- resolves an *effective* query: the strict parse when it matches at least one
-- chunk in this workspace, otherwise the relaxed parse.
-- ---------------------------------------------------------------------------
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
  bounds as (
    select
      least(greatest(coalesce(p_candidate_count, 30), 1), 200) as candidates,
      least(greatest(coalesce(p_limit, 10), 1), 100) as max_rows
  ),
  query_terms as (
    select
      public.mnemos_lexical_query(p_query) as strict_tsq,
      public.mnemos_lexical_query_relaxed(p_query) as relaxed_tsq
  ),

  -- Choose the query once. The existence probe is index-backed and runs as the
  -- caller, so it can only ever see chunks RLS already permits.
  effective_terms as (
    select
      case
        when q.strict_tsq is null then null
        when exists (
          select 1
          from public.chunks probe
          where probe.workspace_id = p_workspace_id
            and probe.content_tsv @@ q.strict_tsq
        ) then q.strict_tsq
        else coalesce(q.relaxed_tsq, q.strict_tsq)
      end as tsq
    from query_terms q
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
    cross join effective_terms q
    cross join bounds b
    where q.tsq is not null
      and c.workspace_id = p_workspace_id
      and c.content_tsv @@ q.tsq
    order by ts_rank_cd(c.content_tsv, q.tsq) desc, c.id
    limit (select candidates from bounds)
  ),

  -- ---- semantic retriever ----------------------------------------------
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
  -- from the original paper and is a constant, not a tuned parameter.
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
  'Hybrid (lexical + semantic) retrieval over one workspace, fused with Reciprocal Rank Fusion. The lexical retriever matches all query terms when possible and relaxes to term-OR only when the conjunction matches nothing in the workspace. SECURITY INVOKER: RLS applies. Superseded/archived passages are excluded unless p_include_superseded is true.';

revoke all on function public.hybrid_search_chunks(uuid, text, vector, integer, integer, boolean)
  from public, anon;
grant execute on function public.hybrid_search_chunks(uuid, text, vector, integer, integer, boolean)
  to authenticated;

revoke all on function public.mnemos_lexical_query_relaxed(text) from public, anon;
grant execute on function public.mnemos_lexical_query_relaxed(text) to authenticated;
