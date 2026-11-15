# ADR-0007 — API contract and error-envelope conventions

**Status:** Accepted
**Date:** 2026-11-15

## Context

The frontend must handle failures predictably, and future agents/services
will call the same API. Without one agreed response shape, every client
re-implements error parsing and correlation.

## Decision

1. **Versioned prefix** `/api/v1`; unversioned `/health` and `/ready` aliases
   exist for infrastructure probes only and are excluded from OpenAPI.
2. **Success** returns the resource payload directly (`200/201`); collections
   return `{"items": [...], "total": n}`; deletes return `204`.
3. **Errors** always use one envelope:
   `{"error": {"code", "message", "request_id", "details"?}}`.
4. **Validation failures** are `422` with per-field `details`
   (`[{"path", "message"}]`), never a raw Pydantic dump.
5. **Correlation**: `X-Request-ID` is accepted only if it is a safe opaque
   token, otherwise a UUID is generated; it is echoed in the header *and* the
   error payload.
6. **Domain errors** are typed exceptions mapped centrally (`app/core/errors.py`);
   route handlers never construct `JSONResponse` for failures.
7. **Unhandled exceptions** return a generic `internal_error` with the request
   id; stack traces, SQL and paths are never returned.

## Alternatives considered

- **RFC 7807 Problem Details** — good standard, but requires extra mapping for
  FastAPI validation errors and adds a second shape for clients to understand.
  Rejected for now; the envelope carries the same information. Revisit if
  external consumers appear.
- **Per-endpoint error shapes** — rejected: inconsistent and untestable.
- **GraphQL** — rejected: heavier than needed, and the REST surface doubles as
  the future agent tool boundary.

## Consequences

- One place to change error behaviour; one parser in the frontend (`ApiError`).
- `request_id` makes support conversations tractable.
- Codes are stable strings, so clients can branch without string-matching
  messages.
