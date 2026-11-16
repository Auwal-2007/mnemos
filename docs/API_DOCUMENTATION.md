# API documentation

Base path `/api/v1`. Interactive schema at `/docs` and `/openapi.json` — the
OpenAPI document is generated from the code, so it cannot drift; this file
explains what the schema cannot.

---

## Conventions

**Authentication.** `Authorization: Bearer <supabase-access-token>` on every route
except `/health` and `/ready`. A missing or invalid token returns `401` with the
error envelope. It never returns `403` for "no token" — those are different
conditions and the client handles them differently.

**Error envelope.** Every non-2xx response has the same shape:

```json
{ "error": { "code": "...", "message": "...", "request_id": "...", "details": {} } }
```

`code` is stable and safe to branch on; `message` is safe to show a user;
`request_id` matches the `X-Request-ID` header and the server logs.

**Status codes.** `400` validation, `401` unauthenticated, `403` authenticated but
not permitted, `404` not found *or* not visible to you (deliberately
indistinguishable — a `403` where a resource exists would confirm its existence),
`409` conflict, `422` ingestion rejected, `429` rate limited, `503` dependency
unavailable.

**Rate limiting.** `120` requests per `60 s` per caller (token subject, or address
when anonymous). `429` carries `Retry-After`. Health and readiness are exempt.

---

## Routes

### Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness. Always cheap, never rate-limited. |
| GET | `/ready` | Per-dependency readiness; reports `degraded` rather than failing. |

### Identity

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | Current profile from the verified token. |
| PATCH | `/me` | Update display name and locale. |
| GET | `/me/preferences` | Theme, density, retention options. |
| PUT | `/me/preferences` | Replace preferences. |

### Workspaces

| Method | Path | Notes |
|---|---|---|
| GET | `/workspaces` | Only workspaces the caller belongs to. |
| POST | `/workspaces` | Creator becomes owner via a database trigger. |
| GET | `/workspaces/{id}` | Member only. |
| PATCH | `/workspaces/{id}` | Owner/editor. |
| DELETE | `/workspaces/{id}` | Owner only. Refused if sources are cited. |
| GET | `/workspaces/{id}/members` | Member only. |

### Knowledge

| Method | Path | Notes |
|---|---|---|
| GET | `/knowledge/workspaces/{id}/sources` | Processing status included. |
| POST | `/knowledge/workspaces/{id}/sources/upload` | Multipart. 50 MB ceiling, allowed types enforced server-side. Accepts `Idempotency-Key`. |
| POST | `/knowledge/workspaces/{id}/sources/note` | A typed note is a first-class source. |
| GET | `/knowledge/sources/{id}` | Detail with current version. |
| GET | `/knowledge/sources/{id}/versions` | Full version chain. |
| POST | `/knowledge/sources/{id}/versions/upload` | New version; the previous becomes superseded, not deleted. |
| POST | `/knowledge/sources/{id}/versions/note` | |
| GET | `/knowledge/sources/{id}/chunks` | Chunk list with offsets. |
| GET | `/knowledge/chunks/{id}/provenance` | The record the EvidencePanel renders. |
| GET | `/knowledge/sources/{id}/download` | Signed URL. |
| DELETE | `/knowledge/sources/{id}` | Refused while cited. |
| POST | `/knowledge/sources/{id}/index` | Extract, chunk, embed. Idempotent. |
| POST | `/knowledge/sources/{id}/reindex` | Safe to repeat. |
| POST | `/knowledge/workspaces/{id}/search` | Hybrid retrieval, no generation. |

### Conversations and answers

| Method | Path | Notes |
|---|---|---|
| GET | `/conversations/workspaces/{id}` | |
| POST | `/conversations/workspaces/{id}` | Title required. |
| GET | `/conversations/{id}` | |
| GET | `/conversations/{id}/messages` | Ordered by `sequence_number`. |
| POST | `/conversations/workspaces/{id}/ask` | Retrieve → generate → persist. An abstention is a `200` with `status: "abstained"`, not an error. |
| GET | `/conversations/answers/{id}` | Answer with claims and per-claim citations. |

### Verification and memory

| Method | Path | Notes |
|---|---|---|
| POST | `/memory/answers/{id}/verify` | `method`: `lexical_overlap` (default) or `model`. |
| GET | `/memory/workspaces/{id}/corrections` | |
| POST | `/memory/workspaces/{id}/corrections` | Creates a **proposal**. Nothing changes yet. |
| POST | `/memory/corrections/{id}/review` | Approve/reject. Self-review refused by a trigger. |
| POST | `/memory/corrections/{id}/apply` | Creates a new revision; the original is preserved and linked. |
| GET | `/memory/workspaces/{id}/conflicts` | |
| POST | `/memory/workspaces/{id}/conflicts/detect` | Writes conflict rows. |
| POST | `/memory/conflicts/{id}/resolve` | Mark resolved or dismiss, with a note. |

### Agents

| Method | Path | Notes |
|---|---|---|
| POST | `/agents/workspaces/{id}/ask` | Orchestrator plans, delegates, composes. Returns the trace. |
| GET | `/agents/orchestrations/{id}` | Recorded trace, read from the database. |
| GET | `/agents/workspaces/{id}/orchestrations` | History. |

`agent_role` accepts `orchestrator`, `retrieval_specialist`,
`memory_specialist`, `verification_specialist`.

---

## Contracts worth understanding

**An abstention is not an error.** `POST .../ask` returns `200` with
`answer.status = "abstained"` and an `abstention_reason`. Returning `4xx` would
make a correct behaviour look like a client mistake and would encourage callers to
retry it.

**Degradation is data.** `degraded_reason` is non-null when something was missing.
Consumers should surface it; ignoring it turns a weak answer into an apparently
strong one.

**Provenance is mandatory.** Every citation carries `provenance_id`, `chunk_id`,
`source_id`, `version_number` and `information_status`. There is no response shape
in which a claim exists without a resolvable source — that is enforced by the
domain model, not by convention.

**Corrections are a lifecycle, not an update.** `POST /corrections` proposes;
`review` approves; `apply` creates a revision. There is deliberately no endpoint
that overwrites a record in place.
