# ADR-0006: Vector storage — pgvector on Supabase

- **Status:** Proposed — partially validated in Phase 2C
- **Date:** 2026-11-15

## Context

MNEMOS requires semantic vector storage and retrieval for personal
knowledge, co-located with relational data and provenance so that
evidence links remain consistent. Supabase supports the pgvector
extension, subject to availability and dimension limits.

## Decision (proposed)

Use pgvector on Supabase PostgreSQL for embedding storage and similarity
search, with embeddings generated via the OpenRouter adapter (model
configurable). This keeps vectors, knowledge items, and provenance in
one database with RLS enforcement.

## Alternatives considered

- **Dedicated vector database (e.g. Pinecone, Qdrant):** rejected for
  now — adds a second system, cost, and consistency challenges without
  a documented requirement. Revisit if scale or latency demands it.
- **No vector search (keyword only):** rejected — semantic retrieval is
  core to the research objectives.

## Consequences

- Positive: single database, transactional consistency with provenance,
  RLS applies to vectors, lower operational burden.
- Negative: pgvector performance and dimension limits may constrain
  embedding model choices; large-scale ANN may need tuning.
- Validation required: confirm pgvector availability on the target
  Supabase project and test embedding dimensions before committing.
  Status remains `Proposed` until validated.

## Phase 2C update (2026-11-15)

The pgvector half of this decision has now been **validated locally**, and the
embedding-generation half has been **split out** into ADR-0010.

Verified in the local PostgreSQL 16.2 harness with pgvector 0.6.2:

- `create extension vector` succeeds;
- `vector(N)` enforces its dimension (`expected 3 dimensions, not 2`);
- HNSW with `vector_cosine_ops` builds and orders correctly;
- `<=>` ordering behaves as documented;
- RLS applies to a `SECURITY INVOKER` similarity function: a non-member and a
  member querying a foreign workspace both receive zero rows.

Not verified: pgvector availability on a **live Supabase project** (no
credentials in this environment). That single fact is why this ADR stays
`Proposed`: the decision is sound and locally demonstrated, but "Supabase has
pgvector enabled" has not been observed here. Promoting it requires running
`scripts/verify-migrations.py` against the project and recording the output.

The clause "embeddings generated via the OpenRouter adapter" is superseded by
ADR-0010, which separates the embeddings endpoint from chat completions.
