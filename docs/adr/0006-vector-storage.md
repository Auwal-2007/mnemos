# ADR-0006: Vector storage — pgvector on Supabase

- **Status:** Proposed
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
