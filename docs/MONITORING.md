# Monitoring

What is observable today, and what is not instrumented. Do not read this as a
description of a working observability stack — no metrics backend, no tracing
system and no alerting were deployed.

---

## 1. What exists

**Health and readiness**

| Endpoint | Meaning |
|---|---|
| `GET /api/v1/health` | Process is alive. Never rate-limited. |
| `GET /api/v1/ready` | Dependencies reachable; reports `degraded` per dependency. |

`/ready` is the correct probe for a load balancer. `/health` answering 200 while
the database is unreachable is expected — liveness and readiness answer different
questions on purpose.

**Structured logs**

`app/core/logging.py` emits one line per event with the request id. Retrieval
logs passage count, whether hybrid search ran, and whether superseded material
was included; generation logs the model id, token counts and outcome; failures
log the provider error class.

**Execution traces**

Every agent run and orchestration is persisted (`agent_executions`,
`orchestration_runs`) with latency, token counts and per-step detail. This is the
closest thing to tracing the system has: it is queryable per answer, not
aggregated across the fleet.

## 2. Signals worth watching

| Signal | Where | Why it matters |
|---|---|---|
| Abstention rate | `answers.status = 'abstained'` | A sudden rise means retrieval broke, or the corpus genuinely lacks coverage |
| Degraded rate | `answers.degraded_reason is not null` | Rising means a provider is failing or embeddings are unconfigured |
| Verification verdicts | `claim_verifications.verdict` | Climbing `unsupported` means generation and evidence have drifted apart |
| Retrieval latency | logged per request | Degradation usually means index bloat or a cold cache |
| Provider errors | logs, by class | Sustained 429s mean the quota is too low for the workload |
| Open conflicts | `conflicts.status = 'open'` | A growing backlog means disagreements are not being adjudicated |
| Token spend | `agent_executions.total_tokens` | The only cost signal the system has |

## 3. What is not instrumented

- No Prometheus, OpenTelemetry or equivalent. No metrics endpoint.
- No distributed tracing. Request ids correlate logs within one process.
- No alerting rules; nothing pages anyone.
- No dashboard over the tables above — the queries are hand-written.
- No error aggregation or grouping; errors appear as log lines.

## 4. Cost

Token usage is recorded per execution. **No cost figure exists**: the provider's
per-token prices are not captured, and inventing them would be a fabrication. Cost
must be computed from the provider's own billing dashboard against the recorded
token counts.

No budget enforcement is implemented. The rate limiter bounds request volume per
caller, which indirectly bounds spend, but there is no per-workspace quota.

## 5. If you add monitoring

The minimum useful additions, in order:

1. Export the counts in §2 as metrics and alert on the *rates*, not the totals.
2. Record provider price per model in configuration and compute cost from
   `total_tokens` — do this only from real price data.
3. Add a per-workspace token budget with a hard stop, since that is the failure
   that costs money.
