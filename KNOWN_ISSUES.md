# Known issues

Ordered by severity. Every entry states the evidence for it, so it is a finding
rather than a worry.

Severity: **P0** security or data integrity · **P1** core workflow broken ·
**P2** important functionality degraded · **P3** minor.

---

## P1 — Blocked by the environment (no code defect)

**K-01. No live provider has ever been called.**
`api.openrouter.ai` and `*.supabase.co` are unreachable from this sandbox
(measured: connection fails, while GitHub, npm and PyPI respond). No API key or
Supabase project exists. Consequence: generation, embedding, verification-by-model
and every hosted-database property are unverified against reality. The code paths
are unit-tested against fakes, which proves the logic, not the integration.
*Action: provide credentials in a network-enabled environment and re-run the
checklist in `docs/DEPLOYMENT.md` §7.*

**K-02. Nothing has been deployed.**
No host, no domain, no production database. Production verification is therefore
zero, and `docs/RELEASE_STATUS.md` records that.

## P2 — Real limitations in the implementation

**K-03. Evidence sufficiency is judged by an inadequate signal.**
The abstention floor (0.25, `ts_rank_cd`) was calibrated on a held-out split and
achieves 0.750 abstention accuracy — but the calibration showed an *answerable*
question scoring 0.011 while an *unanswerable* one scored 0.100. No single lexical
threshold separates the two populations, so roughly **27% of answerable questions
are refused**. Evidence: `docs/EVALUATION.md` §6.4.
*Fix: requires an embedding provider (semantic similarity) or a model-based
sufficiency judgement. Both are blocked by K-01.*

**K-04. Lexical-only retrieval understates the system.**
With no embedding provider, `hybrid_search_chunks` runs its lexical branch alone.
Every retrieval figure in `docs/EVALUATION.md` is a floor for a hybrid deployment,
not an estimate of it. Semantic retrieval has never executed.

**K-05. No answer-level quality measurement.**
Answer correctness, faithfulness, claim-level attribution and unsupported-answer
rate are unmeasured. They appear in `results.json` under `blocked_metrics` with
reasons, rather than being omitted silently.

**K-06. The conventional baseline outperforms MNEMOS on recall, MRR and nDCG.**
Recall@5: baseline 1.000, MNEMOS 0.842 (0.947 with history enabled). MNEMOS leads
only on precision (0.402 vs 0.286), which is the expected cost of filtering
superseded material. This is reported as a negative result, not tuned away.
Evidence: `docs/EVALUATION.md` §5.3.

**K-07. Rate limiting is per-process.**
With N workers the effective limit is N × `RATE_LIMIT_REQUESTS`, and a restart
resets it. It bounds a single runaway client, not fleet-wide abuse. A distributed
limiter belongs at the edge. Evidence: `docs/SECURITY.md` §6.

**K-08. Uploaded documents are parsed in-process without sandboxing.**
PDF extraction runs in the API process. A malicious document (zip bomb, deeply
nested object, malformed cross-reference table) has not been tested and would be
processed in-process. Real residual risk for multi-tenant use.
*Fix: sandbox the extractor in a subprocess with a memory and time cap.*

**K-09. No prompt-injection testing against a live model.**
Mitigations are structural (instruction/data separation, no tool access from
content, grounded-only output, controlled memory writes) and are reviewed and
unit-tested. The *effect* of an adversarial document cannot be observed without a
model.

**K-10. Ingestion has no durable job state.**
Indexing runs inside the request. A process restart mid-index leaves the source in
`processing` with no automatic recovery; re-running index is idempotent and safe.
A long document can exceed a client timeout.

**K-11. Verification is a separate request, not part of answering.**
`POST .../ask` does not verify; the client calls
`POST /memory/answers/{id}/verify` and then reads the detail record. The
orchestrator page now does this automatically after each answer, so per-claim
support is shown in the main workflow. Two consequences remain: an API client
that skips the call stores unverified claims, and verification costs one extra
round trip per answer. Fold verification into the ask endpoint only if the added
latency is acceptable.

## P3 — Gaps in coverage and polish

**K-12. No browser-rendered verification.**
Chromium could not be downloaded. Responsive behaviour is asserted structurally,
not observed. No screenshots in this repository are trustworthy as evidence of
appearance.

**K-13. No end-to-end journey test.**
The nine journeys in the brief (registration, ingestion, answering, specialist,
orchestration, correction, conflict, cross-user denial, mobile) are not automated
as browser E2E tests. Cross-user denial *is* covered as a database-level test.

**K-14. No load, soak, or performance testing at scale.**
Latency was measured in the evaluation harness on 8 documents. No throughput
figures exist and none should be inferred.

**K-15. No dependency CVE audit.**
`pip-audit` / `npm audit` were not run against the locked dependency sets.

**K-16. Semantic retrieval UI state is untested.**
The frontend renders `hybrid: false` and `degraded_reason`, but because no
provider exists, that branch has only been exercised with fabricated responses in
component tests — never with a real degraded server response.

**K-17. Streaming does not exist.**
No SSE endpoint, no `StreamingResponse`. The UI shows an in-flight indicator, not
token-by-token output. This is deliberate: simulated chunking would be fake
streaming. Adding real streaming means adding a real SSE endpoint first.

**K-18. No notification system.**
Operation outcomes (upload finished, indexing complete, conflict detected) are
shown in-place. There is no cross-session notification feed or push delivery.

**K-19. Settings are partially wired.**
Profile and preferences are connected. Model configuration is not user-editable,
deliberately — it is deployment configuration, not a per-user setting.
