# Backup and recovery

Supabase manages backups for the hosted database; this document records what that
covers, what it does not, and how to recover the parts Supabase does not own.

---

## 1. What holds state

| Store | Contents | Backed up by |
|---|---|---|
| PostgreSQL | Workspaces, sources, versions, chunks, embeddings, provenance, conversations, answers, claims, corrections, conflicts, executions | Supabase automated backups (plan-dependent) |
| Supabase Storage | Original uploaded files | Supabase (plan-dependent) |
| OpenRouter | Nothing persists | n/a |
| Application processes | Nothing persists | n/a |

The backend is stateless: any instance can serve any request. Losing an instance
loses no data.

## 2. The asymmetry that matters

The database is the authoritative record, and **it holds derived data that cannot
be reconstructed from the originals alone**:

- **Chunk boundaries** are reproducible: re-running the chunker with the same
  config produces the same chunks. Safe to rebuild.
- **Embeddings** are *not* reproducible bit-for-bit. Re-embedding the same text
  can return a different vector, and it costs money. A restore that loses
  embeddings means re-paying for them.
- **Provenance records, corrections and conflicts are irreplaceable.** They record
  human decisions. No re-derivation recovers a correction somebody approved.
- **Conversations and answers** are irreplaceable for the same reason.

So a storage-only backup is insufficient. The PostgreSQL dump is the backup that
matters.

## 3. Taking a backup

```bash
pg_dump "$SUPABASE_DB_URL" --format=custom --file=mnemos-$(date +%F).dump
```

Before relying on one, verify it restores into a scratch database:

```bash
createdb restore_test
pg_restore --dbname=restore_test mnemos-2026-11-16.dump
psql restore_test -c "select count(*) from public.provenance_records;"
```

An unverified backup is a hypothesis.

## 4. Restore procedure

1. Provision the target database and enable `pgvector` before restoring; a dump
   containing `vector(N)` columns will fail without the extension.
2. Restore the dump.
3. Restore Storage objects for the `sources` bucket.
4. Re-apply any migrations newer than the dump — the dump has the schema as of
   its date.
5. Verify:
   ```sql
   select count(*) from public.workspaces;
   select count(*) from public.provenance_records;
   select count(*) from public.chunks where content_tsv is null;  -- expect 0
   ```
6. Confirm RLS survived: `select relname from pg_class where relrowsecurity is false and relkind='r' and relnamespace='public'::regnamespace;` must return no rows.

A restored database with RLS disabled is worse than an empty one, because it looks
correct.

## 5. Rebuilding derived data

If embeddings are lost but chunks remain:

```bash
curl -X POST "$API/api/v1/knowledge/sources/$ID/reindex" -H "Authorization: Bearer $TOKEN"
```

This is idempotent and safe to repeat. Retrieval keeps working during a partial
rebuild — sources without embeddings are simply found lexically, and the response
says `hybrid: false`.

## 6. Retention and deletion

- Deleting a source removes its chunks and provenance. Because provenance is
  referenced by claims, deletion is refused while an answer still cites it rather
  than silently orphaning a citation.
- Corrections are never deleted; rejection is a status, not a removal. This is
  deliberate: the record that a correction was proposed and refused is itself
  history.
- **No retention policy is configured.** Nothing expires automatically, and no
  automated deletion job exists.

## 7. What is not implemented

- No scheduled backup verification job.
- No documented RPO/RTO. Supabase's backup cadence is plan-dependent and was not
  inspected, because no Supabase project existed in the environment where this was
  written.
- No tested restore of a production-sized database.
- No point-in-time recovery procedure documented, as availability depends on plan.

**None of this has been exercised.** No backup was taken and no restore was
performed, because there was no live database to back up.
