# Troubleshooting

Symptoms, causes and fixes. Each entry states how to confirm the diagnosis, so it
does not become folklore.

---

## The frontend loads but every request fails

**Confirm:** browser devtools → the failing request's URL. If it points at
`localhost` from a deployed site, the build had no `VITE_API_BASE_URL`.

**Fix:** rebuild with `VITE_API_BASE_URL` set. Vite inlines it at build time, so
changing `.env` without rebuilding has no effect.

## `401` on every authenticated request

**Confirm:** decode the token's `exp`. An expired token and an invalid one look
identical in the error body.

**Causes:** expired session and no refresh; `SUPABASE_ANON_KEY` from a different
project than the one that issued the token; clock skew.

**Fix:** sign in again. If it persists, compare the backend's `SUPABASE_URL`
project ref with the frontend's `VITE_SUPABASE_URL` — a mismatch validates
nothing.

## `/ready` reports degraded but data still appears

That is intended. A deployment without an embedding provider still retrieves
lexically. The response says which dependency is missing; the UI repeats it as
"Semantic search is not configured".

## Retrieval returns nothing for a question I know is answerable

**Confirm:** call search directly.

```bash
curl -s -X POST "$API/api/v1/knowledge/workspaces/$WS/search" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"your question"}' | jq '.total, .hybrid, .degraded_reason'
```

- `total: 0` and the words are rare → the source may not be indexed. Check
  `sources.processing_status` is `ready` and that chunk rows exist.
- `total: 0` for a natural-language question → confirm the relaxed-query fallback
  is present: `select count(*) from pg_proc where proname='mnemos_lexical_query_relaxed';`
  must be 1. Without it, migration `20260104000000` did not run and every term is
  AND-ed.
- `hybrid: false` → no embedding provider; lexical only.

## An answer is marked degraded

Read `degraded_reason`; it names the specific gap. Common values: embedding
provider unconfigured, retrieval ran lexically, verification unavailable. The
answer is still stored, and it is still citable — it is just weaker than a normal
one, and it says so.

## An answer was refused (abstained)

Not an error. `abstention_reason` explains it. Two usual causes: nothing in the
corpus matches, or the best match fell below the evidence floor.

The floor is 0.25 on the retriever's own strength (`ts_rank_cd`). It was
calibrated on a held-out split and it is known to be an imperfect signal — see
`docs/EVALUATION.md` §6.4, where an answerable question scored below an
unanswerable one. A quarter of answerable questions can be refused at this
threshold. That is a measured limitation, not a misconfiguration.

## A correction cannot be approved

**Cause:** self-review. A database trigger blocks a user approving their own
correction.

**Fix:** have a different workspace member review it. This is enforced in the
database, not the UI, so it cannot be bypassed by calling the API directly.

## Upload fails with a validation error

Check, in order: extension is one of `.pdf`, `.md`, `.markdown`, `.txt`; MIME type
matches the extension; size under 50 MB. Unsupported formats are refused rather
than silently accepted, and the message names the reason.

## Migration fails: `type "vector" does not exist`

`pgvector` is not enabled on that database. `create extension vector;` first.
Without it, semantic retrieval cannot function; the application degrades to
lexical rather than crashing.

## `EMBEDDING_DIMENSION` mismatch

Symptom: inserts fail with a dimension error, or a distance query errors.

**Confirm:** make one real embedding call and read the returned vector length.
Do not trust documentation — several providers omit embedding models from their
model listing, and the advertised dimension may not match what the model returns.

**Fix:** set `EMBEDDING_DIMENSION` to the observed length and migrate the column.
Re-embed everything; vectors of different widths are not comparable.

## Rates of 429 from the application itself

The rate limiter, not the provider. Response has `error.code: "rate_limited"` and
a `Retry-After` header. Raise `RATE_LIMIT_REQUESTS` or reduce client concurrency.
Remember the limit is per worker process.

## Tests fail with "pgserver is not available"

The integration tests need an embedded PostgreSQL. Install it, or accept that
those tests skip — they are the ones that prove RLS and retrieval against a real
database, so a skipped run means those properties are unverified for that commit.
