# Environment variables

Every variable the application reads. Defaults are shown where one exists.
Values in the right-hand column are the ones that **must** be set for a working
deployment.

---

## Core

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `APP_ENV` | `development` | recommended | `development` / `production` |
| `APP_NAME` | `mnemos` | no | Service name in logs |
| `APP_DEBUG` | `true` | **set `false` in production** | Verbose errors |
| `APP_HOST` | `0.0.0.0` | no | Bind address |
| `APP_PORT` | `8000` | no | Bind port |
| `APP_LOG_LEVEL` | `INFO` | no | Log verbosity |
| `APP_CORS_ORIGINS` | `http://localhost:5173` | **yes** | Comma-separated allowed origins |
| `API_V1_PREFIX` | `/api/v1` | no | Route prefix |

## Supabase

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `SUPABASE_URL` | — | **yes** | Project URL |
| `SUPABASE_ANON_KEY` | — | **yes** | Browser-safe key, used to validate tokens |
| `SUPABASE_SERVICE_ROLE_KEY` | — | **yes** | Server only. Never export. |
| `SUPABASE_DB_URL` | — | for migrations | Direct PostgreSQL connection |
| `SUPABASE_JWT_SECRET` | — | optional | Legacy HS256 signing secret. Only needed when local verification is possible; asymmetric-key projects are verified through the Auth API with `SUPABASE_URL` + `SUPABASE_ANON_KEY` |
| `SUPABASE_STORAGE_BUCKET_SOURCES` | `sources` | no | Upload bucket |

### How access tokens are verified

The server tries, in order:

1. an in-process cache of tokens verified in the last 60 seconds;
2. a local HS256 signature check — only if `SUPABASE_JWT_SECRET` is set;
3. `GET {SUPABASE_URL}/auth/v1/user` with the anon key — algorithm-agnostic, and
   the only option for projects that sign with asymmetric keys (the default).

A failed local check falls through to step 3 rather than rejecting the request,
because a project that signs with RS256/ES256 fails an HS256 check even for a
perfectly valid session. Outright expiry is rejected locally without a network
call. If nothing is configured, or the Auth API is unreachable, the API answers
**503** with a message saying the problem is server-side — never 401, which would
tell a signed-in user to sign in again.

## OpenRouter (chat)

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | — | **yes** | Bearer key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | no | Gateway base |
| `OPENROUTER_DEFAULT_MODEL` | — | **yes** | Fallback model id |
| `OPENROUTER_ORCHESTRATOR_MODEL` | — | no | Per-role override |
| `OPENROUTER_RETRIEVAL_MODEL` | — | no | Per-role override |
| `OPENROUTER_MEMORY_MODEL` | — | no | Per-role override |
| `OPENROUTER_VERIFICATION_MODEL` | — | no | Per-role override |
| `OPENROUTER_MAX_RETRIES` | `3` | no | Transport retries |
| `OPENROUTER_TIMEOUT_SECONDS` | see config | no | Request timeout |

No model id is hardcoded in business logic; every call resolves its model from
configuration. See `docs/MODEL_CONFIGURATION.md`.

## Embeddings

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `EMBEDDING_BASE_URL` | `https://openrouter.ai/api/v1/embeddings` | no | Embedding endpoint |
| `EMBEDDING_API_KEY` | — | for semantic search | May equal the OpenRouter key |
| `EMBEDDING_MODEL` | — | for semantic search | e.g. an OpenRouter-served embedding model |
| `EMBEDDING_DIMENSION` | `1536` | **must match the model** | Vector width |
| `EMBEDDING_BATCH_SIZE` | `32` | no | Chunks per request |
| `EMBEDDING_MAX_RETRIES` | `3` | no | Transport retries |

**A mismatch between `EMBEDDING_DIMENSION` and the model's real output will fail
at insert time**, because the column is `vector(N)`. Verify the dimension with an
actual call before deploying. Do not infer it from provider documentation.

## Chunking and retrieval

| Variable | Default | Purpose |
|---|---|---|
| `CHUNK_TARGET_CHARS` | `900` | Chunk window size |
| `CHUNK_OVERLAP_CHARS` | `150` | Overlap between windows |
| `RETRIEVAL_DEFAULT_LIMIT` | `10` | Passages returned |
| `RETRIEVAL_CANDIDATE_COUNT` | `30` | Fusion pool per retriever |

## Rate limiting

| Variable | Default | Purpose |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Master switch |
| `RATE_LIMIT_REQUESTS` | `120` | Requests per window per caller |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window length |

In-process counter: with N workers the effective limit is N × this value.

## Frontend (build time)

| Variable | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | yes | API base, e.g. `https://api.example.com/api/v1` |
| `VITE_SUPABASE_URL` | yes | Project URL |
| `VITE_SUPABASE_ANON_KEY` | yes | Browser key |
| `VITE_APP_ENV` | no | Shown in diagnostics |
| `VITE_API_TIMEOUT_MS` | no | Client timeout, default 15000 |

Anything prefixed `VITE_` is compiled into the bundle and is public. **No secret
may ever use a `VITE_` variable.**

## Verifying a configuration

```bash
curl -s localhost:8000/api/v1/ready | jq
```

Each dependency reports its own state. `degraded` names which one is missing;
it does not fail the process, because a deployment without an embedding provider
is still a usable lexical-retrieval deployment and should say so.
