# Deployment

> **Status: not deployed.** No host, no Supabase project and no provider key were
> available in the environment where this was written. Nothing in this file has
> been executed end to end. It is a configuration guide, not a record of a
> successful deployment, and `docs/RELEASE_STATUS.md` says so too.

---

## 1. Components

| Component | Runtime | Notes |
|---|---|---|
| Frontend | Static build (`npm run build` → `frontend/dist`) | React SPA; needs a host that rewrites unknown paths to `index.html` |
| Backend | ASGI app (`uvicorn app.main:app`) | Python 3.11+ |
| Database | Supabase PostgreSQL | 11 migrations must be applied in order |
| Storage | Supabase Storage | Bucket `sources` |
| Auth | Supabase Auth | Email + password |
| Inference | OpenRouter | Chat and embeddings; both configurable |
| Vector | pgvector extension | **Verify availability before relying on it** |

## 2. Prerequisites

1. A Supabase project.
2. `pgvector` enabled: `create extension if not exists vector;` — if this fails on
   your project, semantic retrieval cannot work and the deployment runs
   lexical-only. `RetrievalService` degrades honestly rather than failing, and
   the UI states that semantic search is unavailable.
3. An OpenRouter API key and a chosen chat model, plus an embedding model and its
   dimension.
4. A static host for the frontend and a Python host for the API.

## 3. Database

Apply migrations **in filename order**:

```bash
for f in supabase/migrations/*.sql; do
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$f"
done
```

The `database` CI job does exactly this against a scratch PostgreSQL on every
pull request and then runs 223 assertions over the result
(`scripts/verify-migrations.py`), including that every base table has RLS enabled
and forced.

**Never** run migrations automatically against production from CI. The workflow
validates a scratch database; promotion is a deliberate manual step. There is no
down-migration for the retrieval functions — they are `create or replace` and are
safe to re-apply, but a destructive schema change needs a reviewed plan.

## 4. Backend

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Required environment variables are listed in `docs/ENVIRONMENT.md`. The service
starts without them and reports `degraded` from `/ready`, which is deliberate: a
missing provider should be visible, not fatal.

Health endpoints: `/api/v1/health` (liveness), `/api/v1/ready` (readiness, checks
dependencies).

## 5. Frontend

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://api.example.com/api/v1 \
VITE_SUPABASE_URL=https://project.supabase.co \
VITE_SUPABASE_ANON_KEY=... \
npm run build
```

Serve `dist/` with a SPA rewrite:

```
/*  /index.html  200
```

Only `VITE_*` values reach the browser. A service-role key in any `VITE_`
variable would be published; the CI hygiene job fails if one appears.

## 6. CORS and redirects

- `APP_CORS_ORIGINS` must list the exact frontend origin(s). Credentials are
  allowed, so a wildcard is not an option.
- In Supabase Auth, add the frontend URL to the redirect allow-list, otherwise
  the email confirmation link bounces.

## 7. Deployment checklist

Each item must be observed, not assumed:

- [ ] Migrations applied; `verify-migrations.py` passes against the target DB
- [ ] `select extversion from pg_extension where extname='vector';` returns a row
- [ ] Backend `/ready` reports every dependency healthy
- [ ] An embedding call succeeds and its vector length matches `EMBEDDING_DIMENSION`
- [ ] A chat completion succeeds with the configured model id
- [ ] Frontend build points at the deployed API, not localhost
- [ ] Registration → login → workspace → upload → index → ask → open a citation
- [ ] A second user cannot read the first user's workspace (test the denial)
- [ ] Rate limiting returns 429 under load
- [ ] `Retry-After` and `X-Request-ID` present on error responses

## 8. Rollback

- Application: redeploy the previous build. Stateless, so this is safe.
- Database: migrations are additive except for `create or replace` function
  bodies. Reverting a function means re-applying the previous definition; keep
  the SQL file for the version you are reverting to.
- Storage: uploading a new version of a source is non-destructive; the previous
  version and its provenance remain.
