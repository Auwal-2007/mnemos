# MNEMOS — Architecture Decision Records (Index)

Decisions are recorded here and in `docs/adr/NNNN-title.md`. Status values:
`Accepted`, `Proposed`, `Superseded`.

| ID | Title | Status | Date |
|---|---|---|---|
| [ADR-0001](docs/adr/0001-supabase-platform.md) | Supabase as the managed database platform | Accepted | 2026-11-15 |
| [ADR-0002](docs/adr/0002-frontend-framework.md) | Frontend: React + Vite + TypeScript | Accepted | 2026-11-15 |
| [ADR-0003](docs/adr/0003-backend-framework.md) | Backend: Python + FastAPI + Pydantic v2 | Accepted | 2026-11-15 |
| [ADR-0004](docs/adr/0004-openrouter-integration.md) | OpenRouter integration approach | Accepted | 2026-11-15 |
| [ADR-0005](docs/adr/0005-repository-architecture.md) | Repository architecture | Accepted | 2026-11-15 |
| [ADR-0006](docs/adr/0006-vector-storage.md) | Vector storage: pgvector on Supabase | Proposed (local verification done; remote pgvector unconfirmed) | 2026-11-15 |
| [ADR-0007](docs/adr/0007-api-contract-conventions.md) | API contract and error-envelope conventions | Accepted | 2026-11-15 |
| [ADR-0008](docs/adr/0008-supabase-access-layering.md) | Supabase access layering (repositories + RLS) | Accepted | 2026-11-15 |
| [ADR-0009](docs/adr/0009-frontend-styling.md) | Styling approach: CSS custom properties, no CSS-in-JS | Accepted | 2026-11-15 |
| [ADR-0010](docs/adr/0010-embedding-provider.md) | Embedding provider separated from the chat provider | Accepted | 2026-11-15 |
| [ADR-0011](docs/adr/0011-visual-identity-and-motion.md) | Visual identity, motion system and selected 3D | Accepted | 2026-11-15 |

## How to add a decision

1. Copy the template in `docs/adr/0000-template.md`.
2. Assign the next number; never reuse numbers.
3. Record context, decision, alternatives, consequences, and status.
4. Link it from this index. Mark superseded decisions; do not delete them.

## Phase 3A–3D decisions

| ADR | Title | Status | Summary |
|---|---|---|---|
| [0012](docs/adr/0012-verification-policy.md) | Verification policy — method, thresholds and failure behaviour | Accepted | Two verification methods, each recorded with its verdict; `unverified` kept distinct from `unsupported`; reliability null when nothing was checked; model verification fails closed. |
| [0013](docs/adr/0013-agent-capability-isolation.md) | Agent capability isolation and trace fidelity | Accepted | Agents are roles with declared capabilities, not autonomous loops. Isolation is structural, traces are written by the code that did the work, and skipped is never recorded as succeeded. |
