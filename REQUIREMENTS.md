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
