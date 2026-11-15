# MNEMOS — Requirement Traceability Matrix

**Generated:** 2026-11-15, from direct inspection of the repository at commit
`38da949`. Every status below was established by reading the code, running the
tests, and checking the schema — **not** by trusting a prior completion claim.

Legend: **Implemented** = code exists and is tested. **Partial** = some of the
requirement exists. **Not implemented** = no code path exists.

---

## 1. Functional requirements (proposal objectives)

| ID | Requirement | Implementation | Tests | Status |
|---|---|---|---|---|
| FR-001 | Chat with the central orchestrator | — | — | **Not implemented** |
| FR-002 | Chat directly with specialists | — | — | **Not implemented** |
| FR-003 | Submit documents and notes | `services/ingestion/*`, `api/v1/ingestion.py` (4 routes) | `test_ingestion_*` (77) | **Implemented** |
| FR-004 | Manage personal knowledge | `services/knowledge_service.py`, 6 routes | `test_knowledge_service` (15) | **Implemented** (delete only; no edit/archive) |
| FR-005 | Ask questions about stored information | — | — | **Not implemented** — no retrieval query path |
| FR-006 | Inspect sources supporting answers | `chunks/{id}/provenance` endpoint + `EvidencePanel` | `test_knowledge_service`, live schema test | **Partial** — provenance resolves, but no answer exists to inspect |
| FR-007 | Review knowledge revisions | `document_versions` table + `/versions` endpoint | `test_knowledge_service` | **Partial** — document versions only; no memory revision model |
| FR-008 | System identifies conflicting information | — | — | **Not implemented** |
| FR-009 | User can correct stored knowledge | — | — | **Not implemented** — no correction endpoint or revision write path |
| FR-010 | Explicit insufficient-evidence responses | — | — | **Not implemented** — no generation exists |
| FR-011 | Knowledge items carry provenance | `provenance_records` (RLS forced), `resolve_chunk_provenance` | `test_knowledge_service`, 126 migration checks | **Implemented** |
| FR-012 | Revisions versioned; prior versions inspectable | `document_versions`, `is_current`, `retire_version` | `test_knowledge_service`, integration | **Implemented** (document level) |
| FR-013 | Ownership boundaries enforced | RLS on 11 tables + `deps.py` identity | `test_authorization` (35), RLS checks | **Implemented** |
| FR-014 | Agent execution records with model ID + usage | `openrouter_*_model` settings only | — | **Not implemented** — no execution record table, no adapter |
| FR-015 | Health-check endpoint | `api/v1/health.py` | `test_health`, `test_health_service` | **Implemented** |

## 2. Knowledge pipeline requirements (Phases 2A–2C)

| ID | Requirement | Implementation | Tests | Status |
|---|---|---|---|---|
| FR-2C-1 | Deterministic chunking with exact character ranges | `services/chunking.py` | `test_chunking` (20) | **Implemented** |
| FR-2C-2 | Chunk config + hash recorded | `chunks.metadata`, `chunking_method/version` | `test_chunk_manifest` (6) | **Implemented** |
| FR-2C-3 | Refuse to mix chunk shapes | `IndexingService._matches_config` | `test_indexing` (15) | **Implemented** |
| FR-2C-4 | Embeddings via `/embeddings`, chat path refused | `infrastructure/embeddings.py` | `test_embeddings` (22) | **Implemented** |
| FR-2C-5 | Dimension validated before storage | adapter + `embedding_dim` check constraint | `test_embeddings`, live DB | **Implemented** |
| FR-2C-6 | `ready` only on full success | `IndexingService.index_version` | `test_indexing` | **Implemented** |
| FR-2C-7 | Resumable indexing, no duplicates | `list_embedded_chunk_ids`, config compare | `test_indexing` | **Implemented** |
| FR-2C-8 | Explicit, version-scoped re-index | `reindex_version` + endpoint | `test_indexing` | **Implemented** |
| FR-2C-9 | Vector search scoped by RLS | `match_chunks` SECURITY INVOKER | 126 migration checks | **Implemented** (DB function only — **no application caller**) |
| FR-2C-10 | UI honest about non-searchable sources | `status.ts`, `SourceDetailPanel` | `KnowledgePage.test` | **Implemented** |

## 3. Retrieval, generation and agent requirements (Phases 3–4)

| Capability | Code | Schema | Tests | Status |
|---|---|---|---|---|
| Hybrid retrieval (vector + FTS + fusion) | — | — | — | **Not implemented** |
| Grounded answer generation | — | — | — | **Not implemented** |
| Claim-level verification | — | — | — | **Not implemented** |
| Conventional RAG baseline | — | — | — | **Not implemented** |
| Revision-aware memory model | — | — | — | **Not implemented** |
| Conflict detection | — | — | — | **Not implemented** |
| Retrieval Specialist | — | — | — | **Not implemented** |
| Memory Management Specialist | — | — | — | **Not implemented** |
| Evidence Verification Specialist | — | — | — | **Not implemented** |
| MNEMOS Orchestrator | — | — | — | **Not implemented** |
| Execution traces | — | — | — | **Not implemented** |
| Evaluation infrastructure | — | — | — | **Not implemented** |

**No `conversations`, `messages`, `answers`, `claims`, `verification_records`,
`memory_revisions` or `conflicts` table exists.** Only the enum type
`information_status` and provenance supersession columns were created ahead of
the work, both unused.

## 4. Engineering requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| FR-016 | Identity from verified JWT only | **Implemented** | `infrastructure/auth.py`, `test_auth` |
| FR-017 | Foundational data model | **Implemented** | 4 tables, RLS forced |
| FR-018 | Signup provisions profile + workspace | **Implemented** | `handle_new_user()` trigger |
| FR-019 | Private storage, user-scoped paths | **Implemented** | bucket + policies migration |
| FR-020 | Consistent error envelope | **Implemented** | ADR-0007, `test_errors` |
| FR-021 | Application shell + navigation | **Implemented** | `AppShell`, `navigation.ts` |
| FR-022 | Conversation interface (both modes) | **Partial** | UI structure exists; **composer disabled, no persistence** |
| FR-023 | Honest agent directory | **Implemented** | `AgentDirectoryPage`, labelled not-executable |
| FR-024 | Light/dark theme, persisted | **Implemented** | `ThemeProvider`, 28 contrast assertions |
| NFR-001 | Responsive UI | **Partially verified** | decisions asserted in jsdom; **no browser rendering** |
| NFR-002 | RLS data isolation | **Implemented** | 126 migration checks |
| NFR-003 | No secrets in source/bundles | **Implemented** | `verify.sh` secret gate |
| NFR-004 | Input validation, sanitized errors | **Implemented** | validation module, error envelope |
| NFR-005 | Structured logs, no document contents | **Implemented** | `core/logging.py` |
| NFR-006 | mypy strict + tsc strict | **Implemented** | both clean |
| NFR-007 | Lint + types + tests in CI | **Implemented** | `.github/workflows` |
| NFR-008 | Model IDs configurable | **Implemented** | settings only; unused |
| NFR-009 | Bounded retries/timeouts | **Implemented** | embeddings adapter, API client |
| NFR-010 | Versioned migrations | **Implemented** | 6 migrations, idempotent |
| NFR-011 | Requirement traceability | **Implemented** | this document |
| NFR-012 | Docs updated per task | **Implemented** | TRACKER/CHANGELOG per phase |
| NFR-013 | No generic SQL entry point | **Enforced** | repository protocols only |
| NFR-014 | Contrast ≥ 7:1 / 4.5:1 | **Enforced** | 28 assertions from tokens |
| NFR-015 | No axe violations | **Enforced** | 10 audits, 0 violations |
| NFR-016 | Responsive at 5 widths | **Partially verified** | no rendered verification |

---

## 5. Frontend inventory

| Route | Backend integration | Status |
|---|---|---|
| `/` (landing) | none (by design) | **Implemented** |
| `/sign-in` | Supabase Auth | **Implemented** |
| `/app` (dashboard) | `/workspaces`, sources | **Implemented** |
| `/app/knowledge` | full ingestion + indexing + chunks | **Implemented** |
| `/app/sources` | same page | **Implemented** |
| `/app/conversations` | none | **UI only** — no conversation exists |
| `/app/conversations/orchestrator` | none | **UI only** — composer disabled with reason |
| `/app/conversations/agent/:id` | none | **UI only** — composer disabled with reason |
| `/app/agents` | static catalog | **Implemented** (documentation surface) |
| `/app/settings` | `/me/preferences` | **Implemented** |
| `/app/system` | `/health`, `/ready` | **Implemented** |

**Unused backend endpoints:** none — all 25 routes are reachable from either
the UI or a test. `match_chunks()` is a DB function with no application caller
(see §3).

**Dead controls:** none found. Every button either performs an action, is
disabled with a stated reason, or navigates. The disabled composers state why.

---

## 6. Conclusion

The repository implements Phases 0, 1, 2A, 2B, 2C and the visual redesign.

**Phases 3 (retrieval, generation) and 4 (verification, memory revision,
conflict detection, agents, evaluation) are entirely absent.** The build is a
well-tested, honestly-labelled ingestion-and-indexing system with a polished
interface over it — not a retrieval-augmented question-answering system.

Consequently Phase 5's acceptance criterion ("the entire principal user journey
works end to end") **cannot be met**, because the journey stops at step 10: a
user can upload, extract, chunk and index a document, and can inspect its
provenance — but cannot ask a question about it.

This is recorded rather than worked around. See
`docs/phases/phase-5-7-blocked-report.md` for what would be required.
