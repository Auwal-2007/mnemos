# MNEMOS — Requirements

Stable requirement IDs. Traceability: proposal objectives → these
requirements → implementation → tests. Do not invent unrelated product
requirements. Do not renumber or reuse IDs.

## Functional requirements

| ID | Requirement | Source | Phase |
|---|---|---|---|
| FR-001 | User can chat with the central orchestrator | Proposal objectives | Future |
| FR-002 | User can chat directly with individual specialist agents | Proposal objectives | Future |
| FR-003 | User can submit documents and notes | Proposal objectives | Future |
| FR-004 | User can manage personal knowledge (CRUD) | Proposal objectives | Future |
| FR-005 | User can ask questions about stored information | Proposal objectives | Future |
| FR-006 | User can inspect sources supporting generated answers | Proposal objectives | Future |
| FR-007 | User can review knowledge revisions | Proposal objectives | Future |
| FR-008 | System identifies conflicting information | Proposal objectives | Future |
| FR-009 | User can correct stored knowledge | Proposal objectives | Future |
| FR-010 | System returns explicit insufficient-evidence responses | Proposal objectives | Future |
| FR-011 | Knowledge items carry provenance (source, author, timestamp) | Chapters 1–3 methodology | Future |
| FR-012 | Revisions are versioned; prior versions remain inspectable | Chapters 1–3 methodology | Future |
| FR-013 | Every user-owned resource enforces ownership boundaries | Security requirement | Future |
| FR-014 | Agent execution records include model ID and usage metadata | AI integration requirement | Future |
| FR-015 | Health-check endpoint reports service status | Engineering requirement | Phase 0 |

## Non-functional requirements

| ID | Requirement | Source |
|---|---|---|
| NFR-001 | Responsive UI across desktop and mobile | Product requirement |
| NFR-002 | User data isolation via Supabase RLS | Security requirement |
| NFR-003 | No secrets in source code or browser bundles | Security requirement |
| NFR-004 | All API input validated; errors sanitized | Security requirement |
| NFR-005 | Structured logging without secrets or full document contents | Observability requirement |
| NFR-006 | Type-safe backend (mypy strict) and frontend (tsc strict) | Quality requirement |
| NFR-007 | Automated lint, type-check, and tests in CI | Quality requirement |
| NFR-008 | Model identifiers configurable; no hardcoded models | AI integration requirement |
| NFR-009 | Bounded retries and timeouts for external calls | Reliability requirement |
| NFR-010 | Versioned database migrations; no manual-only schema changes | Data requirement |
| NFR-011 | Traceability from requirements to implementation to tests | Process requirement |
| NFR-012 | Documentation updated with every implementation task | Process requirement |

## Out of scope (Phase 0)

All FR-001–FR-014 product capabilities are explicitly out of scope for
Phase 0. Phase 0 delivers FR-015 and the engineering foundation only.

## Phase 1 refinement

The following requirements are now implemented, refined or newly stated as a
result of Phase 1. Existing IDs are unchanged; new IDs are appended.

| ID | Requirement | Status |
|---|---|---|
| FR-015 | Health-check endpoint | **Implemented** — `/api/v1/health`; readiness at `/api/v1/ready` reports integration presence without values |
| FR-016 | Authenticated identity from a verified Supabase JWT only; never from request bodies | **Implemented** — `infrastructure/auth.py`, `api/deps.py` |
| FR-017 | Foundational data: profile, preferences, workspace, membership, each user-owned | **Implemented** — 4 tables, RLS forced |
| FR-018 | Signup provisions profile, default preferences and a personal workspace | **Implemented** — `handle_new_user()` trigger |
| FR-019 | Private storage for source documents with user-scoped paths | **Implemented (bucket only)** — no upload UI or ingestion |
| FR-020 | Consistent API error envelope with request correlation for every failure path | **Implemented** — ADR-0007 |
| FR-021 | Application shell with navigation to Home, Knowledge, Conversations, Agents, Sources, Settings | **Implemented** — `/sources` is an explicit planned placeholder |
| FR-022 | Conversation interface supporting orchestrated (Mode A) and direct specialist (Mode B) modes | **Implemented (structure)** — no model execution, composer disabled with reason |
| FR-023 | Agent directory presenting planned roles honestly, labelled as not operational | **Implemented** |
| FR-024 | Light and dark themes with persisted preference | **Implemented** |
| NFR-013 | No generic SQL entry point may exist in application code (agents included) | **Enforced** — repository protocols only; verified by absence in code review and tests |
| NFR-014 | Contrast: body text ≥ 7:1, muted/UI text ≥ 4.5:1 in both themes | **Enforced** — 28 automated assertions |
| NFR-015 | Accessibility: no axe-detectable violations on shipped pages | **Enforced** — 7 audits, 0 violations |
| NFR-016 | Responsive usability at 1440, 1024, 768, 390 and 360 px | **Partially verified** — layout decisions asserted; pixel rendering not captured (no browser) |

Phase 1 deliberately did **not** implement FR-001–FR-014 (ingestion,
retrieval, agents, orchestration, provenance, revisions, supersession,
conflicts, corrections, evidence-aware answers). They remain future scope.

## Phase 2C — chunking and indexing

- **FR-2C-1** Extracted text is split deterministically into chunks that each
  resolve to an exact character range (and page, when known) in one document
  version.
- **FR-2C-2** Every chunk records the chunking method, version, full
  configuration and content hash, so a corpus can be reproduced exactly.
- **FR-2C-3** Chunks from different configurations are never mixed silently: an
  index request that would mix shapes is refused.
- **FR-2C-4** Embeddings are requested from an embeddings endpoint, with the
  model, dimension, batching, timeout and retry policy configurable. A chat
  endpoint is refused.
- **FR-2C-5** A returned vector whose size differs from the configured
  dimension is rejected before storage; nothing partial is written.
- **FR-2C-6** A source is marked `ready` only when chunking and embedding both
  succeed; otherwise it stays `extracted` with a recorded reason.
- **FR-2C-7** Indexing is resumable: a retry reuses matching chunks and skips
  chunks that already have vectors, and cannot duplicate either.
- **FR-2C-8** Re-indexing is explicit, version-scoped, and never touches the
  original file, its version row, or its extracted text.
- **FR-2C-9** Vector search is scoped by workspace through RLS and a
  `SECURITY INVOKER` function; a non-member receives no rows.
- **FR-2C-10** The UI states plainly when a source is not searchable and never
  implies that an unindexed document has been searched.

- **NFR-2C-1** No hardcoded vector dimension: the column type and the adapter
  check derive from one setting.
- **NFR-2C-2** No embedding call to a chat-completions endpoint, under any
  configuration.

## Phase 3A–3D — retrieval, grounding, verification and agents

Requirements introduced or made concrete by Phases 3A–3D. IDs are appended; the
original FR-001–FR-014 are untouched so the traceability chain to the approved
proposal still holds.

### Phase 3A — hybrid retrieval

- **FR-3A-1** Retrieval combines lexical and semantic ranking into one fused
  result, with the weights configurable rather than hardcoded.
- **FR-3A-2** Each result reports which method matched it (lexical, semantic or
  both), so a weak semantic match cannot be mistaken for a lexical one.
- **FR-3A-3** Superseded and disputed passages are excluded by default and
  included only on explicit request.
- **FR-3A-4** Retrieval is scoped by workspace through RLS and a
  `SECURITY INVOKER` function; a non-member receives no rows.
- **FR-3A-5** Semantic retrieval degrades honestly: with no embedding provider
  configured the system performs lexical retrieval only and says so, rather than
  silently returning lexical results labelled as hybrid.

### Phase 3B — grounded generation

- **FR-3B-1** No evidence means no model call. The system abstains with a reason
  (FR-010) instead of answering from parametric memory.
- **FR-3B-2** A citation that does not resolve to a passage in the evidence set
  invalidates the whole answer; nothing is stored and the attempt fails.
- **FR-3B-3** Every stored claim carries at least one citation, or is recorded
  as having none. A claim cannot be persisted with an invented source.
- **FR-3B-4** A provider failure yields a `failed` execution record and **no**
  answer row. It never yields a fabricated or partial answer.
- **FR-3B-5** Model identity, usage and latency are recorded per execution
  (FR-014); prompt text is not stored.
- **FR-3B-6** The model actually reported by the gateway is recorded separately
  from the model requested, because gateways substitute silently.
- **FR-3B-7** A transport failure surfaces as the domain's own provider error,
  never as a raw library exception, so the API returns an honest status.

### Phase 3C — verification, corrections and conflicts

- **FR-3C-1** Verification records which method produced a verdict; `unverified`
  and `unsupported` are distinct and never conflated.
- **FR-3C-2** An aggregate reliability figure is null when nothing was checked.
  Reporting 0% would imply every claim failed; 100% would imply success.
- **FR-3C-3** Model-based verification fails closed: a provider error or
  unusable output leaves claims unverified rather than assuming support.
- **FR-3C-4** Applying a correction never edits the original. It creates a
  revision, marks the original superseded, and links both directions (FR-012).
- **FR-3C-5** A correction cannot be approved by the person who proposed it.
  This is enforced in the service and by a database trigger (FR-013).
- **FR-3C-6** A correction requires owner or editor membership to apply, and the
  acting user is passed explicitly rather than inferred from session state.
- **FR-3C-7** A detected conflict stores its detection method, score and reason,
  so a reviewer can judge the evidence instead of trusting a verdict (FR-008).
- **FR-3C-8** Each pair of passages yields at most one conflict row, canonicalised
  by provenance order.

### Phase 3D — agents and orchestration

- **FR-3D-1** Each agent role declares its capabilities, and a capability it does
  not hold fails loudly at the seam rather than being merely documented.
- **FR-3D-2** No agent may both produce and approve an answer. The critic cannot
  write, the analyst cannot verify.
- **FR-3D-3** The plan is recorded before execution, so a deviation is visible
  rather than rationalised afterwards.
- **FR-3D-4** A trace step is written only after the work it describes has
  completed, by the code that did the work.
- **FR-3D-5** A skipped specialist is recorded as `skipped` with a reason and
  never as `succeeded`; an unchecked answer is reported as degraded.
- **FR-3D-6** A failed analyst produces no answer and no trace entry claiming
  success.
- **FR-3D-7** Clients may read traces but never write them: a trace a client can
  author is not evidence (FR-013).
- **FR-3D-8** Traces carry results and metadata, not document text or raw prompts.
- **FR-3D-9** No agent has SQL, filesystem or arbitrary network capability. There
  is no configuration that grants one (NFR-013).
