# Database Schema

Authoritative description of the MNEMOS database. Documentation that
disagrees with `supabase/migrations/` is a bug.

**Verified against:** PostgreSQL 16 (local pgserver harness) — Phase 1B
(62 checks) plus Phase 2A (109 checks). **Not verified:** a live Supabase
project, GoTrue, PostgREST and the Storage API.

Migrations, applied in filename order:

| Migration | Contents |
|---|---|
| `20260101000000_initial_schema.sql` | profiles, workspaces, workspace_members, user_preferences; triggers; signup bootstrap |
| `20260101000100_rls_policies.sql` | RLS enable/force, helper functions, grants |
| `20260101000200_storage_sources_bucket.sql` | private `sources` bucket and object policies |
| `20260102000000_knowledge_schema.sql` | sources, document_versions, extracted_contents, extracted_pages, chunks, provenance_records |
| `20260102000100_knowledge_rls.sql` | RLS for the knowledge tables, version immutability trigger |

## Entity relationship

```mermaid
erDiagram
    auth_users ||--|| profiles : "1:1 cascade"
    auth_users ||--|| user_preferences : "1:1 cascade"
    auth_users ||--o{ workspaces : "owns"
    workspaces ||--o{ workspace_members : "has"
    auth_users ||--o{ workspace_members : "belongs"

    workspaces ||--o{ sources : "1:N"
    auth_users ||--o{ sources : "submitted by"
    sources ||--o{ document_versions : "1:N"
    document_versions ||--|| extracted_contents : "1:1"
    document_versions ||--o{ extracted_pages : "1:N"
    document_versions ||--o{ chunks : "1:N"
    chunks ||--|| provenance_records : "1:1"

    sources {
        uuid id PK
        uuid workspace_id FK
        uuid owner_id FK
        source_kind kind
        text title
        text content_hash
        text storage_path
        processing_status processing_status
        text idempotency_key
        jsonb metadata
        timestamptz submitted_at
    }

    document_versions {
        uuid id PK
        uuid source_id FK
        uuid workspace_id FK
        int version_number
        text content_hash
        text storage_path
        extraction_status extraction_status
        bool is_current
    }

    extracted_contents {
        uuid id PK
        uuid document_version_id FK
        text content
        text content_hash
        int char_count
        text extraction_method
        int page_count
    }

    extracted_pages {
        uuid id PK
        uuid document_version_id FK
        int page_number
        int start_offset
        int end_offset
    }

    chunks {
        uuid id PK
        uuid source_id FK
        uuid document_version_id FK
        int chunk_index
        text content
        text content_hash
        jsonb source_location
        text chunking_method
        int chunking_version
        embedding_status embedding_status
    }

    provenance_records {
        uuid id PK
        uuid chunk_id FK
        uuid source_id FK
        uuid document_version_id FK
        jsonb source_location
        information_status information_status
        uuid revision_of FK
        uuid superseded_by FK
        timestamptz submitted_at
    }
```

## Phase 1B tables

### public.profiles

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK, FK → `auth.users.id` ON DELETE CASCADE |
| `email` | `text` | nullable |
| `display_name` | `text` | nullable, 1–80 chars when present |
| `avatar_url` | `text` | nullable |
| `created_at` | `timestamptz` | NOT NULL DEFAULT `now()` |
| `updated_at` | `timestamptz` | NOT NULL DEFAULT `now()`, trigger-maintained |

### public.workspaces

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK DEFAULT `gen_random_uuid()` |
| `owner_id` | `uuid` | NOT NULL FK → `auth.users.id` CASCADE |
| `name` | `text` | NOT NULL, 1–120 chars |
| `slug` | `text` | NOT NULL, `^[a-z0-9]([a-z0-9-]{1,48}[a-z0-9])$` |
| `description` | `text` | nullable, ≤ 2000 chars |
| `created_at` / `updated_at` | `timestamptz` | NOT NULL |

`UNIQUE (owner_id, slug)`; indexes on `owner_id` and `(owner_id, created_at desc)`.

### public.workspace_members

PK `(workspace_id, user_id)`; `role` is the `workspace_role` enum
(`owner`/`editor`/`viewer`). The workspace insert trigger adds the owner row.

### public.user_preferences

`user_id` PK FK → `auth.users`; `theme` in (`system`,`light`,`dark`); `locale`
2–10 chars.

## Phase 2A tables

### public.sources

One row per submitted item. It is a *container*: content lives in
`document_versions`.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK DEFAULT `gen_random_uuid()` |
| `workspace_id` | `uuid` | NOT NULL FK → `workspaces` CASCADE |
| `owner_id` | `uuid` | NOT NULL FK → `auth.users` CASCADE |
| `kind` | `source_kind` | NOT NULL (`document`, `note`) |
| `title` | `text` | NOT NULL, 1–300 chars |
| `original_filename` | `text` | ≤ 255 chars; **NULL for notes**, required for documents |
| `mime_type` | `text` | NOT NULL |
| `size_bytes` | `bigint` | NOT NULL, 0 … 52 428 800 (50 MiB, matches the bucket) |
| `content_hash` | `text` | NOT NULL, `^[0-9a-f]{64}$` |
| `storage_bucket` | `text` | NOT NULL DEFAULT `'sources'` |
| `storage_path` | `text` | NOT NULL, 1–1024 chars, `<user_id>/<...>` |
| `processing_status` | `processing_status` | NOT NULL DEFAULT `pending` |
| `processing_error_code` | `text` | ≤ 64 chars |
| `processing_error_detail` | `text` | ≤ 500 chars, sanitized |
| `processing_attempts` | `integer` | NOT NULL DEFAULT 0 |
| `idempotency_key` | `text` | 8–128 chars |
| `metadata` | `jsonb` | NOT NULL DEFAULT `{}` |
| `submitted_at` | `timestamptz` | NOT NULL DEFAULT `now()` |
| `created_at` / `updated_at` | `timestamptz` | NOT NULL, trigger-maintained |

Constraints beyond the column list:

- `sources_id_workspace_unique UNIQUE (id, workspace_id)` — exists so child
  tables can enforce *same workspace* with a composite foreign key.
- `sources_kind_filename_consistent` — a note cannot carry a filename.
- `sources_idempotency_unique_idx UNIQUE (workspace_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL` — retry safety.

Indexes: `(workspace_id, created_at desc)`, `(owner_id)`, `(processing_status)`.

### public.document_versions

Every submission. **Never updated in place**: a trigger rejects any change to
`content_hash`, `size_bytes`, `storage_path`, `storage_bucket`,
`version_number` or `source_id`, and refuses `is_current` moving `false → true`.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK |
| `workspace_id` | `uuid` | NOT NULL |
| `source_id` | `uuid` | NOT NULL |
| `version_number` | `integer` | NOT NULL ≥ 1, assigned by trigger |
| `content_hash` | `text` | NOT NULL sha256 |
| `size_bytes` | `bigint` | NOT NULL |
| `mime_type` | `text` | NOT NULL |
| `storage_bucket` / `storage_path` | `text` | NOT NULL |
| `extraction_status` | `extraction_status` | NOT NULL DEFAULT `pending` |
| `extraction_method` | `text` | e.g. `plain-text`, `pdf`, `markdown` |
| `extraction_error_code` | `text` | ≤ 64 chars |
| `extraction_error_detail` | `text` | ≤ 500 chars |
| `extracted_at` | `timestamptz` | set when extraction succeeds |
| `indexing_config` | `jsonb` | chunking + embedding configuration used |
| `is_current` | `boolean` | NOT NULL DEFAULT true |
| `idempotency_key` | `text` | 8–128 chars |
| `submitted_by` | `uuid` | FK → `auth.users` ON DELETE SET NULL |
| `submitted_at` / `created_at` / `updated_at` | `timestamptz` | NOT NULL |

- `UNIQUE (source_id, version_number)`
- `document_versions_one_current_idx UNIQUE (source_id) WHERE is_current` —
  at most one current version per source.
- `document_versions_source_workspace_fk (source_id, workspace_id) →
  sources (id, workspace_id)` ON DELETE CASCADE.

### public.extracted_contents

Derived text, kept strictly separate from the original bytes.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK |
| `workspace_id` | `uuid` | NOT NULL |
| `document_version_id` | `uuid` | NOT NULL, **UNIQUE** — one extraction per version |
| `content` | `text` | NOT NULL |
| `content_hash` | `text` | NOT NULL sha256 |
| `char_count` | `integer` | NOT NULL, `= char_length(content)` (checked) |
| `extraction_method` | `text` | NOT NULL |
| `page_count` | `integer` | NOT NULL DEFAULT 0 |
| `metadata` | `jsonb` | parser notes (encoding detected, warnings) |

### public.extracted_pages

Preserves location for multi-page or multi-segment text:
`UNIQUE (document_version_id, page_number)`, half-open
`[start_offset, end_offset)` into `extracted_contents.content`,
`CHECK (end_offset >= start_offset)`.

### public.chunks

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK |
| `workspace_id` / `source_id` / `document_version_id` | `uuid` | NOT NULL |
| `chunk_index` | `integer` | NOT NULL ≥ 0, `UNIQUE (document_version_id, chunk_index)` |
| `content` | `text` | NOT NULL, non-empty |
| `content_hash` | `text` | NOT NULL sha256 of `content` |
| `char_count` | `integer` | NOT NULL, `= char_length(content)` (checked) |
| `source_location` | `jsonb` | NOT NULL; must contain `start_offset` and `end_offset`, and `end_offset >= start_offset` (checked) |
| `chunking_method` / `chunking_version` | `text` / `integer` | NOT NULL |
| `embedding_status` | `embedding_status` | NOT NULL DEFAULT `pending` |
| `metadata` | `jsonb` | NOT NULL DEFAULT `{}` |

A validating trigger (`validate_chunk_relationships`) rejects a chunk whose
`source_id` differs from its version's `source_id`, so a chunk cannot be
attached to the wrong source even if both exist.

### public.provenance_records

The durable citation identity, one row per chunk.

| Column | Type | Constraints |
|---|---|---|
| `id` | `uuid` | PK — this is the `provenance_id` in the contract |
| `workspace_id` / `source_id` / `document_version_id` | `uuid` | NOT NULL |
| `chunk_id` | `uuid` | NOT NULL **UNIQUE** FK → `chunks` CASCADE |
| `source_location` | `jsonb` | must equal the chunk's location (trigger-checked) |
| `information_status` | `information_status` | NOT NULL DEFAULT `current` |
| `revision_of` | `uuid` | FK → `provenance_records` SET NULL |
| `superseded_by` | `uuid` | FK → `provenance_records` SET NULL |
| `resolution_metadata` | `jsonb` | how the location was resolved |
| `submitted_at` | `timestamptz` | must equal the version's `submitted_at` (checked) |
| `created_at` | `timestamptz` | NOT NULL |

`validate_provenance_relationships` rejects a record whose
source/version/location/timestamp disagree with the chunk and version it
claims to describe. Fabricating a citation is therefore a database error, not
a code-review problem.

### public.resolve_chunk_provenance(uuid)

`SECURITY INVOKER` SQL function returning the full provenance contract
(`provenance_id`, `chunk_id`, `source_id`, `document_version_id`,
`workspace_id`, `source_title`, `source_kind`, `version_number`,
`source_location`, `chunk_index`, `information_status`, `revision_reference`,
`superseded_by`, `document_created_at`, `submitted_at`,
`resolution_metadata`). Invoker rights mean the caller's RLS applies: a
foreign chunk resolves to zero rows rather than leaking a title.

## Deletion behaviour

| Deleted | Cascades to | Storage object |
|---|---|---|
| `auth.users` row | profiles, preferences, owned workspaces → all of their knowledge rows | deleted by `handle_user_delete` service call (2B) |
| `workspaces` row | sources → versions → extracted text/pages, chunks → provenance | deleted by the workspace service (2B) |
| `sources` row | versions → extracted text/pages, chunks → provenance | deleted by the ingestion service before the row (2B) |
| `document_versions` row | extracted text/pages, chunks → provenance | never deleted individually (history) |

Nothing cascades *upwards*: deleting a chunk never deletes a source. Provenance
rows always die with their chunk, because a citation without its passage is a
fabrication risk.

## New in Phase 2A — verification

`scripts/verify-migrations.py` [10]–[13] prove, against real PostgreSQL:

- creation of the full chain source → version → extraction → page → chunk →
  provenance, and resolution back to `Paper|1|0|current|1`;
- rejection of a duplicate `chunk_index`, a mismatched `source_id`, a
  cross-workspace chunk, a forged `source_location`, a forged `submitted_at`,
  an invalid hash, and a note carrying a filename;
- version immutability, single-current-version, and preservation of the old
  version's chunks when a new version arrives;
- cascade deletion leaving `0/0/0` orphan rows;
- per-table RLS: cross-user reads return 0, cross-user inserts and deletes are
  refused, users cannot forge chunks or relabel provenance, and `anon` is
  denied on every table with zero grants.
