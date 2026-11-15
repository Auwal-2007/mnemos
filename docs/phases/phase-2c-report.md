# Phase 2C Report — Chunking and Vector Indexing

**Date:** 2026-11-15
**Branch:** `arena/548c24a5-mnemos`
**Scope:** Phase 2C — chunking, embeddings, vector index. No retrieval, no
generation, no agents.

## 1. What was built

A deterministic path from extracted text to retrievable passages, with the
chunking configuration and the embedding model recorded at every step.

```
extracted_contents (text + page map)
   │  deterministic split (paragraph-window, 900/150)
   ▼
chunks  (index, text, offsets, page, config hash, method+version)
   │  isolated embeddings adapter (dimension validated)
   ▼
chunk_embeddings  (vector(N), model id, dimension)  → HNSW cosine index
```

Four decisions carry the phase:

1. **Chunking is deterministic and justified by measurement.** No model is
   involved, so a corpus can be re-chunked and compared. The parameters were
   measured rather than guessed — see §3.
2. **The embedding provider is not the chat provider.** ADR-0010 records why:
   embeddings use `/embeddings`, not `/chat/completions`. The adapter refuses a
   chat path at construction, so the mistake cannot happen silently.
3. **The dimension is configuration, validated twice.** The `vector(N)` column
   uses `app.embedding_dimension`; each returned vector is checked against
   `EMBEDDING_DIMENSION`; a mismatch raises before anything is stored.
4. **`ready` means searchable.** It is set only when chunking *and* embedding
   both succeed, and is re-read from the database before being reported. A
   deployment without embeddings stops at `extracted` and says so.

## 2. Files changed

**Backend (new)**
- `app/services/chunking.py` — algorithm, `ChunkingConfig`, `PageRange`
- `app/services/indexing.py` — `IndexingService` (chunk, embed, orchestrate, reindex)
- `app/infrastructure/embeddings.py` — `EmbeddingProvider` protocol,
  OpenAI-compatible client, error taxonomy
- `app/api/v1/indexing.py` — `index` and `reindex` endpoints
- `tests/unit/test_chunking.py` (20), `test_embeddings.py` (22),
  `test_indexing.py` (15), `test_chunk_manifest.py` (3)

**Backend (modified)**
- `app/core/config.py` — embedding + chunking settings, `is_embedding_configured`
- `app/repositories/knowledge_repositories.py` — `SupabaseEmbeddingRepository`,
  `SupabaseExtractionReader`, `store_extraction` metadata
- `app/domain/knowledge.py` — `Chunk.metadata`
- `app/services/ingestion/pipeline.py` — async, optional indexer, `IndexingOutcome`
- `app/api/deps.py` — indexer wiring (only when embeddings are configured),
  chunking config from settings
- `app/core/config.py` — chunking settings validated at startup (overlap must be
  smaller than the target, or the window would never advance)
- `app/schemas/knowledge.py` — `IndexSourceResponse`, `EmbeddingStatusResponse`
- `tests/integration/test_knowledge_schema_live.py` — 2 new real-DB tests
  (full chunk→vector chain, one-current-version guard)

**Migrations**
- `supabase/migrations/20260102000200_chunk_embeddings.sql`

**Frontend**
- `src/lib/api/knowledge.ts` — `indexSource`, `reindexSource`, `IndexSourceResult`
- `src/features/knowledge/SourceDetailPanel.tsx/.css` — index controls, chunk
  list with character ranges and page numbers, honest "not searchable" copy
- `src/features/knowledge/KnowledgePage.test.tsx` — chunk mocks

**Docs**
- `docs/CHUNKING_AND_INDEXING.md` (new), `docs/adr/0010-embedding-provider.md`
  (new), `docs/DATABASE_SCHEMA.md`, `docs/PROVENANCE_MODEL.md`,
  `.env.example`, `TRACKER.md`, `CHANGELOG.md`

## 3. Measured chunking behaviour

Prose block, 8 879 characters, no blank lines:

| target | overlap | chunks | min / median / max | overhead |
|---|---|---|---|---|
| 600 | 100 | 20 | 395 / 544 / 592 | 1.21× |
| **900** | **150** | **12** | **739 / 888 / 888** | **1.18×** |
| 1200 | 200 | 9 | 591 / 1184 / 1184 | 1.13× |

Paragraph-structured text, 29 038 characters: 40 chunks at 726–728 chars, 1.00×
overhead. These numbers are the justification for the defaults, not a
retrieval-quality claim — retrieval measurement is Phase 3A.

## 4. Commands run and actual results

```
python scripts/verify-migrations.py   → Passed: 126    Failed: 0
cd backend && .venv/bin/pytest -q     → 247 passed
.venv/bin/ruff check app tests        → All checks passed!
.venv/bin/ruff format --check app tests → 62 files already formatted
.venv/bin/mypy app                    → Success: no issues found in 44 source files
cd frontend && npx tsc --noEmit       → clean
npx vitest run                        → 87 passed (10 files)
npm run build                         → built in 2.09s (465 kB JS / 55 kB CSS)
```

Environment probes actually executed before writing the migration:

```
create extension vector                 → OK (0.6.2)
create index ... using hnsw             → OK
insert vector(3) with 2 elements        → ERROR: expected 3 dimensions, not 2
select id, e <=> '[1,2,3]' order by d   → correct ordering
```

## 5. Acceptance criteria — checked individually

| Criterion | Status | Evidence |
|---|---|---|
| Deterministic chunking | Pass | `test_chunking_is_deterministic`; identical hashes over 300 paragraphs |
| Strategy justified | Pass | measured table in §3 + `CHUNKING_AND_INDEXING.md` |
| Method, size, overlap, model id, version recorded | Pass | `metadata.chunking_config` + `chunking_method`/`chunking_version` + `embedding_model` per row |
| Preserves source/version/location/index/hash | Pass | columns + integration test reconstructing every chunk from offsets |
| New versions get new chunks; old provenance not overwritten | Pass | version-scoped operations; `test_reindex_does_not_touch_other_versions` |
| Embedding adapter configurable model | Pass | `EMBEDDING_MODEL` |
| Batching | Pass | `test_respects_the_batch_size` |
| Input + dimension validation | Pass | `test_dimension_mismatch_is_rejected`, empty-vector and count checks |
| Error/rate-limit handling, retries | Pass | 429/timeout retry, 4xx no-retry, bounded attempts |
| Usage tracking | Pass | `prompt_tokens` captured per request (bug found and fixed: was per-vector) |
| Real provider/endpoint verified, not assumed | **Partial** | endpoint and wire format verified from documentation; **no live call** (no key) |
| Separate provider behind an adapter | Pass | ADR-0010 + adapter + chat-path guard |
| Never send embedding calls to a chat endpoint | Pass | `test_chat_endpoint_is_refused` + 2 parametrized cases |
| pgvector verified before creating the column | Pass | probe transcript in §4 |
| Index strategy/operator/metric | Pass | HNSW, `vector_cosine_ops`, cosine, rationale documented |
| Metadata filters / workspace isolation | Pass (workspace) | RLS + `match_chunks` invoker; metadata filtering deferred to 3A with the reason recorded |
| No arbitrary hardcoded dimension | Pass | `app.embedding_dimension` + `EMBEDDING_DIMENSION`, validated 1..16000 |
| `ready` only when complete | Pass | `test_successful_indexing_marks_the_source_ready` + failure tests |
| Partial failures handled | Pass | `test_partial_progress_resumes_without_duplicating` |
| Retries don't duplicate chunks/embeddings | Pass | chunk config check + `list_embedded_chunk_ids` + PK on `chunk_id` |
| Re-indexing with recorded config; no silent replacement | Pass | explicit endpoint; `test_a_different_configuration_refuses_to_mix_chunk_shapes` |
| No mixed dimensions | Pass | column type + per-vector check + DB check constraint |
| Tests: boundaries, overlap, location, dimensions, insertion, retries, duplicates, failure, isolation, re-index | Pass | 60 new backend tests |
| Every chunk resolves to exact source+version | Pass | `resolve_chunk_provenance` (2A) + integration reconstruction |

## 6. Bugs found and fixed during this phase

1. **Usage tokens were summed per vector instead of per request** — the reported
   `prompt_tokens` was N× too large for a batch of N. Caught by
   `test_usage_is_captured`; fixed by accumulating once per request.
2. **Config comparison ignored the actual parameters** — two different
   `target_chars` values with the same `CHUNKING_VERSION` were treated as
   identical, so chunk shapes could have been silently mixed. Caught by
   `test_a_different_configuration_refuses_to_mix_chunk_shapes`; fixed by
   persisting and comparing the full configuration.
3. **`vector` dimension was initially unvalidated per row** — added a
   `embedding_dim` column with a check constraint tied to the declared
   dimension, so a row cannot disagree with its own column type.

## 7. Known limitations and honest gaps

1. **No live embedding call.** No API key exists in this environment, so the
   model's real dimension is unconfirmed. Everything about the request/response
   path is tested against recorded fixtures; the live path is unverified. This
   is the single largest gap in the phase.
2. **pgvector on the target Supabase project is unverified.** The migration
   raises `feature_not_supported` instead of skipping, so a deployment will fail
   loudly rather than silently lose the vector index.
3. **HNSW parameters are defaults chosen by reasoning** (`m=16`,
   `ef_construction=64`), not tuned against a real corpus. Retrieval quality is
   not measured until 3A.
4. **Metadata filtering inside the vector query is deferred.** Filters will be
   applied on joined rows in 3A so a filter cannot drop the RLS scope; this
   costs some performance and is documented rather than hidden.
5. **A re-index invalidates old evidence references.** New chunk rows mean old
   `provenance_records` cascade away. 3C must treat an unresolvable reference as
   unsupported — noted in `CHUNKING_AND_INDEXING.md §7`.
6. **Chunking is character-based**, so languages without spaces or with very
   long sentences will land nearer the 4000-character hard maximum.
7. **Changing `CHUNK_TARGET_CHARS` / `CHUNK_OVERLAP_CHARS` does not
   automatically bump `CHUNKING_VERSION`.** The values are now read from settings
   and recorded in `metadata.chunking_config`, and the indexer refuses to mix
   shapes, so a change is *detected* and refused rather than silently applied.
   But an operator who wants to re-chunk an existing corpus must raise
   `CHUNKING_VERSION` in `app/services/chunking.py` as well; that coupling is
   enforced by a pinned-config test and documented in
   `CHUNKING_AND_INDEXING.md §2`, not automated.

## 8. Next step

Phase 3A — hybrid retrieval: validate → scope → normalise → query embedding →
vector search + lexical full-text search → filters → fusion → ranked evidence
carrying the full provenance contract.
