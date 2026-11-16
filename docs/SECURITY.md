# Security

What is implemented, what was tested, and what remains unverified. Nothing in
this file is a compliance claim.

---

## 1. Authentication

- Supabase Auth issues the tokens; the backend verifies them in
  `app/infrastructure/auth.py`. An unauthenticated request to any protected route
  returns `401` in the standard error envelope and nothing else.
- The service-role key is read only by backend code (`app/infrastructure/supabase.py`)
  and never reaches the browser. Frontend code references only
  `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`; a repository-hygiene CI job
  fails on a service-role key appearing under `frontend/`.
- Tokens are never persisted by the API client (`credentials: 'omit'`), and are
  passed per call rather than held in a module-level variable.

## 2. Authorization

Two independent layers, deliberately:

1. **RLS in PostgreSQL.** All 23 base tables have RLS enabled *and forced*. A
   query that forgets a `WHERE` clause still cannot cross a workspace boundary.
   The `hybrid_search_chunks` function is `SECURITY INVOKER` specifically so RLS
   applies to retrieval.
2. **Explicit service checks.** `RetrievalService._require_member` and its peers
   check membership and raise `403` rather than returning an empty list, so the
   UI can distinguish "not allowed" from "nothing found".

Verified by 223 migration/RLS assertions against a real PostgreSQL and by
`tests/api/test_authorization.py` (53 tests). Isolation tests use two distinct
users and assert the *denial*, not just the absence of data.

## 3. Prompt injection

Uploaded documents and retrieved passages are untrusted input. Controls:

- **Instruction/data separation.** Generation wraps evidence in a delimited block
  and states in the system prompt that text inside it is data, never instruction
  (`app/services/generation.py`). The verification prompt repeats the rule.
- **No tool access from content.** Nothing in the retrieved text can cause a
  database write, a filesystem read, or an outbound request. The generation path
  can only produce text; every downstream action is a separate authorized call.
- **Grounded-only output.** Citations are validated against passages actually
  retrieved; an answer citing an unknown passage is rejected rather than stored.
  This limits injection to "misleading prose", not "fabricated citation".
- **Controlled memory writes.** Corrections are proposals, reviewed by a
  different user, and a database trigger blocks self-approval.

**Not tested:** no adversarial corpus of prompt-injection documents was run,
because doing so requires a live model to observe the effect. The mitigations are
structural, and structural mitigations are what can be verified without one.

## 4. Secrets

- No credentials are committed. `.env` is ignored; `.env.example` holds
  placeholders only.
- A CI hygiene job scans for keys and for service-role material under `frontend/`.
- Logs redact provider keys; the completion and embedding clients never log the
  `Authorization` header.
- **No secret was ever present in this environment**, so the redaction paths are
  unit-tested rather than observed on live traffic.

## 5. File uploads

- MIME and extension allow-list, size ceiling (50 MB), enforced server-side in
  `app/services/ingestion/validation.py` — not only in the browser.
- Storage paths are workspace- and user-prefixed; RLS on `storage.objects`
  restricts reads to the owning workspace.
- Extraction accepts `.pdf`, `.md`, `.txt` only. Unsupported formats are refused
  with an explicit message rather than silently accepted.

**Not tested:** malicious PDFs (zip bombs, deeply nested objects, malformed
cross-reference tables). The parser is not sandboxed, and a hostile document is
processed in-process. This is a real residual risk for a multi-tenant deployment
and is listed in `KNOWN_ISSUES.md`.

## 6. Rate limiting and timeouts

Implemented in `app/core/middleware.py`, added in Phase 6A:

- Fixed-window limit, default 120 requests / 60 s per caller
  (`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_ENABLED`).
- Callers are bucketed by **token subject**, not client address, so users behind
  one NAT do not share a budget.
- Health and readiness probes are exempt. A rate-limited health check would make
  an orchestrator kill a healthy instance.
- Rejections use the standard error envelope with `429` and `Retry-After`.
- The caller table is bounded so it cannot itself become a memory-exhaustion
  vector.

**Limitation, stated plainly:** the counter is in-process. With N workers the
effective limit is N × the configured value, and a restart resets it. This stops
a single runaway client, which is the realistic abuse case here. It is not a
distributed quota and should be supplemented at the edge in any real deployment.

Request timeouts are enforced per call: 15 s default for ordinary requests, 60 s
for uploads and search, 120–180 s for generation and orchestration.

## 7. Security testing performed

| Test | Result |
|---|---|
| Protected route without token → 401 | Passed |
| Cross-user workspace access → denied | Passed (real PostgreSQL, RLS) |
| Non-member retrieval → no rows | Passed |
| Self-approval of a correction → blocked by trigger | Passed |
| Agent capability leakage across roles | Passed (unit) |
| Rate limit enforced / probes exempt | Passed (7 tests) |
| Service-role key absent from frontend | Passed (CI job) |
| Malicious uploaded document | **Not tested** |
| Prompt injection against a live model | **Not tested** (no model) |
| Penetration test | **Not performed** |
| Dependency CVE audit | **Not performed** |

## 8. What this document does not claim

No audit, no penetration test and no third-party review was carried out. The
absence of a finding here means a control was tested and held, or that no test
was run — never that the system is secure in general. The sections marked *not
tested* are the honest boundary.
