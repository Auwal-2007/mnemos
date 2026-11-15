# Phase 2A Report — Provenance-Aware Knowledge Schema

**Date:** 2026-11-15
**Branch:** `arena/548c24a5-mnemos`
**Scope:** Phase 2A only — domain model and migrations. No ingestion, no
extraction, no chunking, no embeddings, no retrieval, no generation.

## 1. What was built

A provenance-aware knowledge schema in which a retrieved passage can always be
resolved to the exact source, exact document version and exact location it came
from — and in which fabricating a citation is a database error rather than a
code-review failure.

Six tables:

| Table | Purpose |
|---|---|
| `sources` | the submitted item (document or note) |
| `document_versions` | every submission; never overwritten |
| `extracted_contents` | derived text, deliberately separate from the original |
| `extracted_pages` | character offsets per page/segment |
| `chunks` | deterministic retrieval units |
| `provenance_records` | durable citation identity, one per chunk |

Design points that carry the research contribution:

1. **Original ≠ extracted ≠ chunked.** Three layers, three tables. The uploaded
   bytes are never mutated, so an extraction or chunking change can never lose
   the original.
2. **Version history is append-only at the database level.** A trigger rejects
   any change to `content_hash`, `size_bytes`, `storage_path`,
   `storage_bucket`, `version_number` or `source_id`, and refuses to move
   `is_current` from `false` back to `true`. Reinstating a superseded document
   requires submitting a *new* version, which is recorded as such.
3. **Same-workspace is a foreign-key property, not a convention.** Composite
   keys (`(id, workspace_id)`) mean a chunk physically cannot reference a
   version in another workspace, even if both UUIDs are valid.
4. **Provenance must agree with its chunk.** A trigger checks that source,
   version, `source_location` and `submitted_at` all match the chunk and
   version they claim. Relabelling a passage is rejected.
5. **Location is structured, not a string.** `source_location` is
   `{start_offset, end_offset, page?}`. Offsets are mandatory; a page is
   present only when the parser produced pages. "Location unavailable" is
   therefore a representable, honest state rather than a blank field.

## 2. Files changed

**Migrations (new)**
- `supabase/migrations/20260102000000_knowledge_schema.sql`
- `supabase/migrations/20260102000100_knowledge_rls.sql`

**Backend (new)**
- `app/domain/knowledge.py` — enums, `Source`, `DocumentVersion`, `Chunk`,
  `SourceLocation`, `ChunkDraft`, `ProvenanceReference`
- `app/repositories/knowledge_repositories.py` — `SupabaseSourceRepository`,
  `SupabaseChunkRepository`
- `app/services/knowledge_service.py` — listing, detail, versions, chunks,
  provenance resolution, deletion
- `app/schemas/knowledge.py` — API contracts
- `app/api/v1/knowledge.py` — six endpoints

**Backend (modified)**
- `app/repositories/base.py` — `SourceRepository` / `ChunkRepository` protocols
- `app/api/deps.py` — repository providers
- `app/api/v1/__init__.py` — router registration
- `tests/api/test_authorization.py` — 6 new protected routes
- `tests/unit/test_knowledge_service.py` — 15 new unit tests

**Verification & docs**
- `scripts/verify-migrations.py` — sections [10]–[13], 47 new checks
- `docs/DATABASE_SCHEMA.md`, `docs/PROVENANCE_MODEL.md`,
  `docs/DATA_DICTIONARY.md` (new)
- `docs/supabase/schema.md` — pointer to the new authoritative document
- `TRACKER.md`, `CHANGELOG.md`

## 3. Commands run and actual results

```
backend/.venv/bin/python scripts/verify-migrations.py
  → Passed: 109    Failed: 0

cd backend && .venv/bin/pytest -q
  → 95 passed, 1 warning

.venv/bin/ruff check app tests        → All checks passed!
.venv/bin/ruff format --check app tests → 46 files already formatted
.venv/bin/mypy app                    → Success: no issues found in 35 source files
```

Environment probes (executed, not assumed):

```
create extension vector   → OK, extversion 0.6.2
create extension pg_trgm  → ERROR: extension "pg_trgm" is not available
```

## 4. Acceptance criteria — checked individually

| Criterion | Status | Evidence |
|---|---|---|
| Source records with all required fields | Pass | section [10] "source row created" |
| Versions never silently overwrite | Pass | [11] "version content is immutable", "retiring a version preserves its chunks" |
| Extracted content distinct from originals | Pass | separate table, [10] "extracted content stored separately"; original bytes never written by any code path |
| Chunks with source/version/index/text/location/length/status | Pass | [10] "chunk created with location"; columns in `DATABASE_SCHEMA.md` |
| Provenance preserves source, version, timestamps, status, revision links | Pass | [10] resolution returns `Paper\|1\|0\|current\|1`; `revision_of`/`superseded_by` columns present |
| Reusable provenance contract | Pass | `ProvenanceReference` + `resolve_chunk_provenance` + `/provenance` endpoint |
| Source-specific location strategies | Pass | offsets required, page optional, documented per format |
| Unavailability representable | Pass | `has_location()`, page nullable, documented |
| FK integrity | Pass | composite FKs; [10] rejects mismatched source and cross-workspace chunk |
| Indexes | Pass | workspace/created, source/version, one-current partial unique |
| Ownership/uniqueness | Pass | `owner_id`, `UNIQUE(source_id, version_number)`, idempotency unique |
| Deletion behaviour | Pass | [12] "deleting a source leaves no orphans" |
| Migration reproducibility | Pass | idempotency section re-applies every migration |
| UUIDs | Pass | `gen_random_uuid()` throughout |
| RLS on every new table | Pass | [13] six tables, enabled + forced |
| Cross-user denial | Pass | [13] all six read checks + insert/delete checks |
| Anon denial | Pass | [13] "anon denied on every knowledge table", zero grants |
| Mermaid ER diagrams | Pass | `DATABASE_SCHEMA.md`, `PROVENANCE_MODEL.md` |

## 5. Known limitations and honest gaps

1. **No live Supabase verification.** Supabase's PostgreSQL is assumed to match
   PostgreSQL 16 semantics; composite FKs, partial unique indexes and
   `SECURITY INVOKER` SQL functions are all standard, but this has not been
   executed against a project.
2. **`pg_trgm` is unavailable** in the local harness. Phase 3A lexical search
   therefore cannot use trigram similarity locally; it will use core `tsvector`
   full-text search, which is available everywhere. This is a real design
   constraint discovered by testing, not a preference.
3. **`resolve_chunk_provenance` is `SECURITY INVOKER`**, so PostgREST must be
   able to execute it as `authenticated`. Verified locally by direct SQL
   role-switching; **not** verified through PostgREST RPC.
4. **Storage object deletion is not implemented yet.** Deleting a source
   removes database rows and their cascade, but the original file in the
   `sources` bucket is removed by the ingestion service in 2B. Until then,
   deletion would leave an orphaned object. This is called out in
   `DATABASE_SCHEMA.md` and is a 2B acceptance criterion.
5. **`information_status` has no transition rules yet.** Every row is created
   `current`; only server-side code will change it, and the permitted
   transitions are defined in 4A.
6. **`extraction_method` is free text** with a length check, not an enum, so a
   future parser does not require a migration. Unknown values are treated as
   "unrecognised parser" by the UI rather than as an error.

## 6. Decisions recorded

| Decision | Alternative | Why this one |
|---|---|---|
| Composite FK for same-workspace | Trigger-only check | A trigger can be dropped or bypassed in a future migration; an FK cannot be violated at all |
| Offsets mandatory, page optional | Store page only | A note has no pages; offsets exist for every text format |
| One provenance row per chunk | Resolve on the fly from joins | A durable id survives re-indexing and gives 3B/3C/4A a stable handle |
| `SECURITY INVOKER` resolution | `SECURITY DEFINER` + manual filter | Invoker rights mean a missed filter cannot leak a foreign row |
| Read-only grants on chunks/provenance | Editor-writable | Citations are the product's integrity surface; only ingestion code may write them |
| No `pg_trgm` dependency | Trigram lexical search | Not available locally; better to use the FTS that is guaranteed present |

## 7. Next step

Phase 2B — controlled ingestion: upload and note endpoints, private storage
writes with safe paths, extraction for plain text/Markdown/PDF, the status
machine, deletion including the storage object, and the submission UI.
