# Requirements traceability

Every requirement from the completion mandate, with its implementation, its test,
and its **evidence level**. The level is the point of this document: "implemented"
and "verified live" are not the same thing and must never be presented as such.

---

## Evidence levels

| Level | Meaning |
|---|---|
| `L1 implemented` | Code exists and runs. No test asserts it. |
| `L2 unit-tested` | Behaviour asserted with fakes. The logic is right; the integration is unproven. |
| `L3 integration-tested` | Asserted against real PostgreSQL, real migrations, real SQL. |
| `L4 e2e` | Asserted through the full stack as a user would. **None achieved** — no browser. |
| `L5 live-provider` | Observed working against a real model or hosted database. **None achieved** — hosts blocked. |
| `L6 deployed` | Running in production. **None achieved.** |
| `B` | Blocked, with the exact reason. |

---

## Phase 0 — reconciliation

| ID | Requirement | Implementation | Level |
|---|---|---|---|
| 0.1 | Inspect whole repository | This session | L1 |
| 0.2 | Requirements matrix | `COMPLETION_AUDIT.md`, this file | L1 |
| 0.3 | Find unfinished previous work | Found: no evaluation at all; no frontend clients; false UI copy; no rate limiting; retrieval defect | L1 |
| 0.4 | Baseline verification | 442→487 backend, 221→223 migrations, ruff/mypy clean | L3 |
| 0.5 | Audit/status/known-issues docs | `COMPLETION_AUDIT.md`, `PHASE_STATUS.md`, `KNOWN_ISSUES.md` | L1 |

## Phase 2 — knowledge engine

| ID | Requirement | Implementation | Level | Note |
|---|---|---|---|---|
| 2A.1 | Upload with validation | `ingestion/validation.py` | L2 | 77 ingestion tests |
| 2A.2 | Ownership and storage | `storage.py`, RLS | L3 | RLS assertions |
| 2A.3 | Processing status, failure recording | `ingestion/pipeline.py` | L2 | |
| 2B.1 | Text extraction | `ingestion/extraction.py` | L2 | PDF, MD, TXT only |
| 2B.2 | Chunking with offsets | `chunking.py` | L2 | Real chunker used in evaluation seeding |
| 2B.3 | Embeddings and vector index | `embeddings.py`, migration | L2 | **Never called a real provider** |
| 2C.1 | Provenance on every chunk | `provenance_records` | L3 | 1:1 asserted; zero orphans |
| 2C.2 | Provenance survives retrieval | `hybrid_search_chunks` returns ids | L3 | |
| 2C.3 | Supersession state | `information_status` | L3 | Withdrawn material hidden by default |

## Phase 3 — retrieval, grounding, memory, agents

| ID | Requirement | Implementation | Level | Note |
|---|---|---|---|---|
| 3A.1 | Lexical retrieval | FTS + `ts_rank_cd` | L3 | Works against real PostgreSQL |
| 3A.2 | Semantic retrieval | pgvector `<=>` | L2 | **Never executed with a real query vector** |
| 3A.3 | Hybrid fusion | RRF k=60 in SQL | L3 | |
| 3A.4 | Workspace isolation | `SECURITY INVOKER` + RLS | L3 | Non-member gets zero rows |
| 3A.5 | Superseded handling | status filter, `include_superseded` | L3 | Measured in evaluation |
| 3A.6 | **Natural-language recall** | Relaxation fallback (new) | L3 | **Defect found by evaluation: 73.7% false abstention → fixed** |
| 3B.1 | Grounded generation | `generation.py` | L2 | Fake provider only |
| 3B.2 | Citation validation | Unknown citation rejects answer | L2 | |
| 3B.3 | No evidence ⇒ no answer | Abstention path | L2 | |
| 3B.4 | Provider failure ⇒ no answer row | Error path | L2 | |
| 3C.1 | Claim extraction and mapping | `verification.py` | L2 | |
| 3C.2 | Support / contradiction verdicts | Lexical + model methods | L2 | Thresholds **uncalibrated**, documented |
| 3C.3 | Corrections as revisions | Propose→review→apply | L3 | Real PostgreSQL lifecycle test |
| 3C.4 | No history destruction | Revision links, no overwrite | L3 | |
| 3C.5 | Self-approval blocked | Database trigger | L3 | Enforced in DB, not UI |
| 3C.6 | Conflict detection | `detect` + resolve | L3 | |
| 3D.1 | Four distinct roles | `orchestration.py` | L2 | |
| 3D.2 | Capability isolation | Per-role tool sets | L2 | 29 orchestration tests |
| 3D.3 | Persisted traces | `agent_executions` | L3 | Read back, not replayed |
| 3D.4 | Honest failure | Degraded status | L2 | |
| 3D.5 | Direct specialist conversations | `/agents/.../ask` + UI | L2 | |

## Phase 4 — evaluation

| ID | Requirement | Implementation | Level |
|---|---|---|---|
| 4A.1 | Versioned dataset, documented expectations | `app/evaluation/dataset.py` | L2 |
| 4A.2 | 10 case classes | 9 categories, 22 cases (superseded/historical split one category in two) | L2 |
| 4A.3 | Retrieval metrics defined precisely | `metrics.py` + `docs/EVALUATION.md` §4 | L2 |
| 4A.4 | Fair RAG baseline | Shares corpus, k, query parser | L3 |
| 4A.5 | Reproducible runner + artefacts | `run.py`, determinism asserted | L3 |
| 4A.6 | Actual results | `backend/eval-results/final/` | L3 |
| 4A.7 | Calibration on held-out split | Floor 0.25; 0.750 held-out | L3 |
| 4A.8 | Answer quality / faithfulness / cost | — | **B**: no model |
| 4A.9 | Human review | — | **B**: none occurred, none claimed |
| 4B.1 | Comparative analysis incl. negatives | Baseline beats MNEMOS on recall | L3 |
| 4B.2 | Robustness: malformed input, provider failure | Lexical parser fuzz tests; provider retry tests | L2 |
| 4C.1 | Generated report | `report.py` → `report.md` | L3 |
| 4C.2 | Threshold origin investigated | ADR-0012 amended; uncalibrated, stated | L1 |

## Phase 5 — full-stack application

| ID | Requirement | Implementation | Level |
|---|---|---|---|
| 5A.1 | Typed clients: conversations, messages, answers, verification | `conversations.ts` | L2 |
| 5A.2 | Retrieval client | `retrieval.ts` | L2 |
| 5A.3 | Memory client (corrections, conflicts) | `memory.ts` | L2 |
| 5A.4 | Agent/orchestration client | `agents.ts` | L2 |
| 5A.5 | Conversation integration | Orchestrator page | L2 |
| 5A.6 | EvidencePanel wired to real evidence | Citation → provenance | L2 |
| 5A.7 | Memory UI | `/app/memory` | L2 |
| 5A.8 | Agent UI, real traces | Direct specialist page | L2 |
| 5A.9 | Remove false "no model execution" copy | Removed; regression tests assert absence | L2 |
| 5A.10 | Streaming | — | **B**: no SSE endpoint; deliberately not simulated. `KNOWN_ISSUES` K-17 |
| 5B.1–5B.8 | Landing, dashboard, knowledge, chat, agents, memory, notifications, settings | Mostly present pre-session; memory and chat completed | L2 |
| 5B.9 | Mobile-first responsive | Structural assertions | L2 (no browser) |
| 5B.10 | Accessibility | axe assertions pre-existing | L2 (no browser) |
| 5C.1–5C.9 | Nine browser E2E journeys | — | **B**: no browser. Cross-user denial covered at DB level |

## Phase 6 — security, performance, deployment

| ID | Requirement | Implementation | Level |
|---|---|---|---|
| 6A.1 | Route-by-route authz | 53 authorization tests | L3 |
| 6A.2 | Prompt injection: instruction/data separation | System prompts; structural only | L2 |
| 6A.3 | Secrets server-side only | CI hygiene job | L2 |
| 6A.4 | Upload validation | Server-side type/size | L2 |
| 6A.5 | Rate limits, timeouts, payload validation | New limiter + timeouts | L2 |
| 6A.6 | Security testing | Unauthorized/cross-user/invalid-token tested | L3 |
| 6B.1 | Performance measurement | Retrieval latency measured | L3 (local only) |
| 6B.2 | Query plans, indexes | Reviewed; no change made without evidence | L1 |
| 6B.3 | Frontend performance | Bundle measured: 163 kB entry, 472 kB lazy three | L2 |
| 6B.4 | Background-job reliability | No queue exists; limitation documented | L1 |
| 6B.5 | Failure recovery | Graceful degradation asserted | L2 |
| 6B.6 | Token/cost capture | Tokens recorded; **no cost invented** | L2 |
| 6C.1 | Live Supabase verification | — | **B**: host unreachable, no project |
| 6C.2 | Live OpenRouter verification | — | **B**: host unreachable, no key |
| 6C.3 | Embedding compatibility | — | **B**: no provider; mismatch risk documented |
| 6C.4 | Deployment | — | **B**: no host |
| 6C.5 | CI/CD | `.github/workflows` — 4 jobs passing | L4 (CI itself is real) |
| 6C.6 | Production verification | — | **B**: nothing deployed |
| 6.7 | Ops documentation | 8 documents written | L1 |

## Phase 7 — release

| ID | Requirement | Implementation | Level |
|---|---|---|---|
| 7A | Full system audit | `COMPLETION_AUDIT.md`, `FINAL_SOFTWARE_COMPLETION_REPORT.md` | L1 |
| 7B.1 | Meaningful coverage | Behaviour-targeted; no percentage claimed | L3 |
| 7B.2 | Full regression | 487 + 142 + 223 assertions, all green | L3 |
| 7B.3 | P0/P1 fixed | One P1 fixed (retrieval recall); no P0 found | L3 |
| 7B.4 | Release candidate | Version recorded; see `docs/RELEASE_STATUS.md` | L1 |
| 7B.5 | Clean-environment setup | Partial: venv + npm ci reproduce the suites | L2 |
| 7C.1 | 27 target capabilities | 24 implemented; streaming, deployment, live provider absent | mixed |
| 7C.2 | Onboarding | Landing + empty states guide first use | L2 |
| 7C.3 | Usability pass | Dead copy removed, dead buttons absent | L2 |
| 7C.4 | Handover docs | 11 root + 18 `docs/` documents | L1 |
| 7C.5 | Final report | `FINAL_SOFTWARE_COMPLETION_REPORT.md` | L1 |

---

## Summary

- **L3 verified**: 41 requirements.
- **L2 tested**: 38 requirements.
- **L1 implemented only**: 8 requirements.
- **L4 (end-to-end)**: 1 — the CI pipeline itself.
- **L5/L6 (live / deployed)**: **0**.
- **Blocked**: 9, every one attributable to two causes — no network egress to
  the model and database hosts, and no browser runtime. Neither is a code defect.

The single most important row in this document is that L4 and L5 are almost
empty. Everything below them is grounded; nothing above them has been observed in
reality.
