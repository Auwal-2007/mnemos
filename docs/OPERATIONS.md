# Operations

Day-two concerns: what runs, what to watch, what to do when something breaks.

---

## 1. Request path

```
client → CORS + request id → rate limit → auth (Supabase token)
       → route → service → repository → PostgreSQL (RLS applies)
                                   ↘ OpenRouter (chat or embeddings)
```

Every request carries `X-Request-ID`, echoed in the response and in every log
line for that request. When a user reports a failure, that id is the fastest way
to find its logs.

## 2. Failure behaviour, by component

| Failure | Observable behaviour | User sees |
|---|---|---|
| Embedding provider down | Retrieval continues lexically; `hybrid: false` | "Semantic search is temporarily unavailable; results are lexical only." |
| Chat provider down | Generation raises; no answer row is written | An error, with retry where the error is retryable |
| Chat provider 429 | Retried with backoff, then reported | "The model provider is rate-limiting requests." |
| Database unreachable | `/ready` fails; requests 5xx | A retryable error |
| Verification provider down | Answer is stored, marked degraded | Answer with the verification gap stated |
| Rate limit exceeded | 429 + `Retry-After` | "Too many requests. Please slow down." |

Nothing degrades silently. A degraded answer says what is missing in
`degraded_reason`, and the UI renders it.

## 3. Background processing

There is no queue and no worker. Ingestion and indexing run inside the request
that triggered them, because introducing a queue would be a new failure surface
with no demonstrated need at this scale.

Consequences, stated honestly:
- A long indexing job keeps an HTTP request open, bounded by the client timeout.
- A process restart during indexing leaves a source in `processing`. There is no
  automatic recovery; `POST /knowledge/sources/{id}/index` re-runs it, and
  indexing is idempotent, so re-running is safe.
- There is no retry policy beyond the provider-level retries.

This is a real limitation, listed in `KNOWN_ISSUES.md`. If ingestion volume grows,
the correct change is a durable job table with a claim/lease pattern — not a
broker.

## 4. Routine operations

**Re-index a source** (safe, idempotent):
```bash
curl -X POST "$API/api/v1/knowledge/sources/$ID/reindex" -H "Authorization: Bearer $TOKEN"
```

**Verify an answer's claims:**
```bash
curl -X POST "$API/api/v1/memory/answers/$ID/verify" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"method":"lexical_overlap"}'
```

**Detect conflicts** in a workspace:
```bash
curl -X POST "$API/api/v1/memory/workspaces/$WS/conflicts/detect" -H "Authorization: Bearer $TOKEN"
```

## 5. Running the checks

```bash
cd backend
.venv/bin/python -m pytest -q                     # 487 tests
.venv/bin/python ../scripts/verify-migrations.py  # 223 assertions, real PostgreSQL
.venv/bin/ruff check app && .venv/bin/python -m mypy app

cd ../frontend
npx tsc --noEmit && npx vitest run && npm run build

cd ../backend
.venv/bin/python -m app.evaluation.run --label ops  # evaluation snapshot
```

## 6. Capacity notes

Measured locally, single process, 8 documents: retrieval p50 is single-digit
milliseconds. **No load test was run** — there are no throughput numbers for
concurrent users, and none should be inferred from the latency figures.

Known scaling limits:
- Retrieval cost grows with corpus size; the lexical side is a GIN index scan,
  the semantic side a sequential distance computation unless an HNSW index is
  present.
- Rate limiting is per-process (see `docs/SECURITY.md` §6).
- Generation latency dominates any answer: it is a full model round trip.
