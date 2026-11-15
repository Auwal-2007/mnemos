# ADR-0001: Supabase as the managed database platform

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

MNEMOS needs a PostgreSQL database with authentication, file storage,
row-level security, and vector search. The project decided to use
Supabase (managed PostgreSQL platform) instead of independently
provisioning and maintaining a conventional PostgreSQL server. A second
database would add operational complexity without a justified requirement.

## Decision

Use Supabase PostgreSQL as the sole database platform, with Supabase
Authentication, Supabase Storage, Row Level Security, versioned
migrations, and pgvector (subject to validation, ADR-0006). Application
access goes through Supabase client libraries and controlled
repositories; schema changes only via migrations in `supabase/migrations/`.

## Alternatives considered

- **Self-managed PostgreSQL:** rejected — operational burden (backups,
  upgrades, HA) is unjustified for this project; Supabase provides the
  same Postgres with managed operations.
- **Separate database (e.g. dedicated vector DB):** rejected — no
  documented requirement; pgvector co-locates vectors with relational
  data and provenance.
- **SQLite for local dev:** rejected as a primary strategy — diverges
  from production semantics (RLS, pgvector, Auth). Local development
  targets the Supabase project or a Supabase local stack.

## Consequences

- Positive: managed Postgres, Auth, Storage, RLS, and migrations in one
  platform; reduced operational burden.
- Negative: platform dependency; Supabase limits (storage, egress, RLS
  performance) must be monitored. Replaceability is moderate — data
  remains standard PostgreSQL, so migration away is feasible but
  non-trivial.
- Follow-up: validate pgvector availability and embedding dimensions
  (ADR-0006); implement RLS policies with the initial schema.
