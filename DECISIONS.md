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
| [ADR-0006](docs/adr/0006-vector-storage.md) | Vector storage: pgvector on Supabase | Proposed | 2026-11-15 |
| [ADR-0007](docs/adr/0007-api-contract-conventions.md) | API contract and error-envelope conventions | Accepted | 2026-11-15 |
| [ADR-0008](docs/adr/0008-supabase-access-layering.md) | Supabase access layering (repositories + RLS) | Accepted | 2026-11-15 |
| [ADR-0009](docs/adr/0009-frontend-styling.md) | Styling approach: CSS custom properties, no CSS-in-JS | Accepted | 2026-11-15 |

## How to add a decision

1. Copy the template in `docs/adr/0000-template.md`.
2. Assign the next number; never reuse numbers.
3. Record context, decision, alternatives, consequences, and status.
4. Link it from this index. Mark superseded decisions; do not delete them.
