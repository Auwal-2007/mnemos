# Storage Strategy

Supabase Storage holds user-submitted original documents. Original files
and extracted text have separate responsibilities and lifecycles.

## Principles

1. **Private buckets:** all buckets are private by default; access via
   signed URLs with short expiry.
2. **User-scoped paths:** object keys include the owner ID, e.g.
   `user/{owner_id}/sources/{source_id}/{filename}`. Storage RLS
   policies enforce that users can only access their own prefix.
3. **Validation:** file size limits and allow-listed MIME types enforced
   server-side before upload; content inspection where practical.
4. **Separation of concerns:** originals (immutable) vs. extracted text
   (derived, stored in Postgres). Deleting a knowledge item deletes or
   archives its originals and derived text per retention rules.
5. **No public URLs:** never expose bucket-public URLs for personal
   documents.

## Planned buckets (Phase 1 — not yet created)

- `sources` (private) — original user-submitted documents.

## Lifecycle

- Upload → validate → store original → extract text → record provenance.
- Correction → new revision; originals retained for audit unless the
  user explicitly deletes them.
- Deletion → remove originals, derived text, and vectors; record the
  deletion in execution/audit metadata.

## Phase 0 status

Strategy documented only. No buckets created, no uploads implemented.
