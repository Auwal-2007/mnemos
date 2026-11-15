# Phase 2B Report — Controlled Document Ingestion

**Date:** 2026-11-15
**Branch:** `arena/548c24a5-mnemos`
**Scope:** Phase 2B — ingestion only. Chunking and embeddings (2C) are not
implemented; sources currently stop at `extracted`.

## 1. What was built

A single, ordered ingestion pipeline that turns a file or a note into a
versioned source whose original is stored privately and whose text has been
extracted into a separate record.

The three properties that matter most:

1. **The client cannot choose the parser.** The format is detected from the
   bytes (`%PDF-` magic, ZIP magic, UTF‑8/UTF‑16 decoding), and a file whose
   contents disagree with its declared type or extension is rejected with
   `type_mismatch`. A text file renamed `.pdf` never reaches the PDF parser.
2. **Every failure has a defined end state.** Storage failure: no rows.
   Version-creation failure: the stored object is deleted and the source is
   marked failed. Extraction failure: the original is kept, the error code is
   recorded on the version and shown to the user, and the status is `failed` —
   never `ready`.
3. **Notes are versioned sources, not strings.** A note goes through the same
   validation, storage, hashing and extraction path as a file, so later phases
   can cite it identically.

## 2. Files changed

**Backend (new)**
- `app/services/ingestion/validation.py` — format detection, filename safety,
  storage paths, note validation
- `app/services/ingestion/extraction.py` — extractor protocol + registry,
  plain-text / Markdown / PDF extractors, rebased page offsets
- `app/services/ingestion/pipeline.py` — the lifecycle and its failure paths
- `app/infrastructure/storage.py` — private storage adapter (`PrivateStorage`
  protocol + Supabase implementation, delete + signed URL)
- `app/api/v1/ingestion.py` — six endpoints
- `tests/unit/test_ingestion_validation.py` (38), `test_ingestion_extraction.py`
  (19), `test_ingestion_pipeline.py` (20),
  `tests/integration/test_knowledge_schema_live.py` (3)

**Backend (modified)**
- `app/repositories/knowledge_repositories.py` — `store_extraction`
- `app/schemas/knowledge.py` — ingestion request/response contracts
- `app/api/deps.py` — `get_ingestion_pipeline`
- `app/api/v1/__init__.py` — router registration
- `pyproject.toml`, `requirements.txt` — `python-multipart`, `pypdf`

**Frontend (new)**
- `src/lib/api/knowledge.ts` — API calls incl. a multipart upload path that
  reuses the same error normalization
- `src/lib/api/useSources.ts` — workspace-scoped source loading
- `src/features/knowledge/{SourceSubmitPanel,SourceList,SourceDetailPanel}.tsx`
  + CSS, `status.ts`, `KnowledgePage.test.tsx` (9 tests)

**Frontend (modified)**
- `src/features/knowledge/KnowledgePage.tsx/.css` — rebuilt around real data
- `src/lib/api/types.ts` — knowledge contracts
- `src/app/navigation.ts` — Sources is now available
- `src/app/AppRoutes.tsx` — `/sources` renders the workspace
- `src/app/App.test.tsx` — the "sources is planned" test now asserts the real
  surface

**Docs**
- `docs/INGESTION_PIPELINE.md` (new), `TRACKER.md`, `CHANGELOG.md`

## 3. Commands run and actual results

```
cd backend && .venv/bin/pytest -q
  → 175 passed, 1 warning
.venv/bin/ruff check app tests        → All checks passed!
.venv/bin/ruff format --check app tests → 55 files already formatted
.venv/bin/mypy app                    → Success: no issues found in 40 source files

python scripts/verify-migrations.py   → Passed: 109    Failed: 0

cd frontend && npx tsc --noEmit       → clean
npx vitest run                        → 87 passed (10 files)
npx vitest run src/app/accessibility  → 7 passed (0 axe violations)
npm run build                         → built in 2.08s (462 kB JS / 53 kB CSS)
```

## 4. Acceptance criteria — checked individually

| Criterion | Status | Evidence |
|---|---|---|
| Text, Markdown and PDF ingestion | Pass | extractor tests; `test_text_document_...`, `test_markdown_document_...`, PDF structural tests |
| Note creation | Pass | `test_note_is_a_versioned_source_not_a_string` + UI test |
| Ownership enforced | Pass | `test_forbidden*` in pipeline tests; RLS checks [13] |
| Accurate statuses | Pass | `test_status_progression_is_ordered_and_accurate`; the UI renders the real value only |
| Error handling | Pass | 6 distinct reject codes + 5 extraction codes, each with a user-facing message |
| Duplicate/retry behaviour | Pass | idempotency header asserted in the UI test; unique index in the DB |
| Original preservation | Pass | bytes stored before any row; extraction failure keeps them; deletion removes them |
| Source → content traceability | Pass | integration test reconstructs the chunk text from stored offsets |
| MIME + extension validation | Pass | `test_client_cannot_lie_about_pdf/text`, `test_forged_mime_is_rejected...` |
| Size limits | Pass | `test_oversized_file_rejected`, bucket limit matches |
| Filename normalization | Pass | 9 parametrized cases incl. traversal and NUL bytes |
| Safe paths | Pass | `storage_path_for` rejects non-UUID ids; path built server-side |
| Private bucket | Pass | bucket `public=false`, user-scoped policy (Phase 1B), verified |
| User-scoped ownership | Pass | `owner_id` from the token only |
| Safe parsing | Pass | pypdf only; no execution, no extraction to disk |
| Clear rejections | Pass | every code has a specific message, no stack traces |
| Extensible extraction | Pass | registry keyed by detected format |
| PDF page boundaries preserved | Pass | per-page segments; offsets rebased and clamped |
| Empty/corrupt/encrypted/no-text/oversized | Pass | one test each |
| Status machine | Pass | 8 states, ordered transitions asserted |
| Errors without secrets | Pass | messages are static strings; codes ≤ 64 chars |
| API with validation + ownership | Pass | 6 endpoints, all behind `AuthContextDep` |
| Real submission UI | Pass | upload + note tabs, four honest feedback states |
| No fake documents/counts | Pass | empty state test asserts absence of sample data; counts derive from the list |
| Deletion lifecycle | Pass | storage first, then cascade; `0/0/0/0` orphans in the integration test |
| Responsive | Pass (code-level) | media queries at 767/1023; no pixel capture (no browser) |

## 5. Known limitations and honest gaps

1. **No live Supabase Storage call.** The adapter is tested against a fake;
   the real `storage3` upload/download/sign path is unverified without
   credentials. The signed-URL response shape is handled for both `signedURL`
   and `signedUrl` because that key has changed between client versions — this
   guess is unverified and is the most likely place for a runtime surprise.
2. **`python-multipart` and `pypdf` are new dependencies.** `pypdf` is pure
   Python and widely used; both are pinned in `requirements.txt`.
3. **No OCR.** A scanned PDF fails with `no_text_layer` and a clear message.
4. **No antivirus scanning.** Documents are parsed, never executed, but no
   malware scan runs.
5. **Files are buffered in memory** up to 50 MiB before validation, so peak
   memory per concurrent upload is bounded but real.
6. **No automatic retry.** A failed extraction stays failed until the user
   re-submits; this is deliberate (a deterministic parser would fail the same
   way) but means a transient storage fault needs a manual retry.
7. **Status stops at `extracted`.** Without 2C there are no chunks, so
   `chunking`/`indexing`/`ready` are never reached. The UI states this
   explicitly rather than implying the corpus is searchable.
8. **`createNoteVersion` sends placeholder `workspace_id`/`title`** because the
   note-version endpoint derives both from the source. This is untidy but
   harmless; a dedicated request schema would be cleaner.

## 6. Decisions recorded

| Decision | Alternative | Why |
|---|---|---|
| Detect format from bytes | Trust `Content-Type` | The header is attacker-controlled; a wrong parser is a security bug |
| Reject on declared/detected mismatch | Silently re-interpret | Silent re-interpretation makes the stored MIME type a lie |
| Storage write before the DB row | DB row first | A row pointing at missing bytes is unrecoverable; an unreferenced object is cleanable |
| Keep originals on extraction failure | Delete on failure | The user's document must never be destroyed by a parser bug |
| Delete storage before DB rows | DB first | A failed deletion is retryable; a cascade with surviving bytes leaks |
| No automatic retry | Retry N times | Deterministic failures would just repeat; retries belong to the user |

## 7. Next step

Phase 2C — deterministic chunking with a recorded configuration, an embedding
adapter that talks to the provider's real embeddings endpoint at a verified
dimension, and pgvector indexing that only marks a source `ready` when every
chunk is embedded.
