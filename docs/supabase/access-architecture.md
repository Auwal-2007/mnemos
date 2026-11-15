# Supabase Access Architecture

How data access is layered so that neither the browser nor an AI agent can
bypass authorization.

## Layers

```
React component
   └── lib/api client (typed, bearer token attached by the auth context)
          └── FastAPI route (validates input, resolves identity)
                 └── application service (authorization policy)
                        └── repository interface (narrow, pre-declared operations)
                               └── Supabase PostgREST client (user-scoped token)
                                      └── PostgreSQL + RLS (final authority)
```

## Three clients, three privilege levels

| Client | Key | RLS | Used for |
|---|---|---|---|
| User client | caller's access token (anon key + `postgrest.auth(token)`) | enforced as that user | all user-scoped reads/writes |
| Public client | anon key | enforced as `anon` (no access) | nothing privileged; kept for future public reads |
| Service client | service-role key | **bypassed** | migrations and explicitly authorized server jobs only |

`get_service_client()` is never injected into a route dependency; routes use
`get_auth_context()`, which builds a **user** client from the verified token.

## Non-negotiables enforced in code

1. Identity comes only from a verified JWT (`app/infrastructure/auth.py`).
   No route accepts a `user_id` from the request body as proof of identity.
2. `WorkspaceService.create_workspace()` takes `owner_id` from the identity,
   never from the payload.
3. Repository interfaces expose named operations only. There is no
   `execute(sql)` method, so no caller — including a future agent — can run
   arbitrary SQL.
4. RLS is the final authority: even if application checks were bypassed, the
   database rejects cross-user access (verified by 62 harness checks).
5. Service-role credentials exist only in server environment variables and
   are never referenced in frontend code (enforced by review + CI env check).

## Authorization policy (application layer)

| Operation | Required role |
|---|---|
| List/get workspace | membership (any role) |
| Update workspace | owner or editor |
| Delete workspace | owner |
| List members | membership (any role) |
| Update own profile / preferences | self only |

Denials return `403 forbidden` for unauthorized-but-existing resources and
`404` only when the resource genuinely does not exist, so existence is not
leaked to non-members.

## Token handling

- Frontend: Supabase JS keeps the session (`persistSession`, `autoRefreshToken`,
  PKCE). The access token is attached per request by the API client.
- Backend: HS256 verification against `SUPABASE_JWT_SECRET`, requiring `sub`
  and `exp`. `alg: none` and wrong-secret tokens are rejected (tested).
- Tokens are never logged, cached, or stored server-side.

## Enabling authentication locally

1. `cp .env.example .env`
2. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`,
   `SUPABASE_SERVICE_ROLE_KEY` (server only).
3. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` for the browser
   (anon key only — never the service-role key).
4. Create a user via Supabase Auth (dashboard or app sign-up). The signup
   trigger provisions the profile, preferences and default workspace.
