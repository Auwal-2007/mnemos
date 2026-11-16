# Retrieval and grounding

How a question becomes a cited answer, and what the system refuses to do along
the way. This document describes Phases 3A–3D as built and verified.

It is deliberately organised around **invariants** rather than components,
because the components are replaceable and the invariants are the product. Each
invariant names the test that defends it.

## The path, in one diagram

```
question
   │
   ├─ membership check ────────────────► 403 (not a member) / 404 (no workspace)
   │
   ├─ hybrid retrieval
   │     ├ lexical  (Postgres full-text over chunks)
   │     └ semantic (pgvector cosine over chunk_embeddings, if configured)
   │     └ fused by weighted rank, superseded excluded by default
   │
   ├─ no passages? ──► ABSTAIN, reason returned, **no model call**
   │
   ├─ generation (JSON mode, evidence in one delimited block)
   │     ├ unknown citation ──► reject the whole answer, store nothing
   │     ├ provider error ────► 502 + `failed` execution, **no answer row**
   │     └ malformed output ──► reject, store nothing
   │
   ├─ persist answer + claims + claim_citations + execution record
   │
   ├─ verification (optional)
   │     ├ lexical_overlap   (always available, free)
   │     └ model_judgement   (if configured; fails closed)
   │
   └─ response: answer, claims, citations, execution, verification, agent trace
```

## Invariants

### I1 — No evidence means no model call

If retrieval returns nothing, the system abstains with a stated reason. It does
not ask the model to try anyway. A model asked a question with no evidence will
answer from its training data, and that answer would be indistinguishable in the
UI from a grounded one.

*Defended by:* `test_generation.py::test_no_evidence_means_no_provider_call`.

### I2 — A citation must resolve, or the answer is rejected

The model's output is checked against the evidence set it was given. A citation
naming a provenance id outside that set invalidates the **entire** answer:
nothing is persisted, and the attempt fails with `MalformedGenerationError`.

The alternative — dropping the bad citation and keeping the claim — would leave a
claim that looks supported but is not.

*Defended by:* `test_generation.py::test_unknown_citation_invalidates_the_answer`.

### I3 — Provider failure produces no answer

A completion failure yields a `failed` execution record and no `answers` row. The
transcript records that the question was asked and that no answer was produced.
There is no partial answer and no retry that silently substitutes a different
model.

*Defended by:* `test_generation.py` provider-error tests; the API maps it to 502.

### I4 — `unverified` is not `unsupported`

| Verdict | Means |
|---|---|
| `supported` | Checked, and the evidence supports it |
| `partially_supported` | Checked, mixed — treated as not supported |
| `unsupported` | Checked, and the evidence does not support it |
| `unverified` | **Nobody checked** |

These are different facts. Merging the last two would tell a user that an
unchecked claim had been checked and failed.

*Defended by:* `test_verification.py` — no resolvable evidence, provider error
and malformed model output each leave the claim `unverified`.

### I5 — Reliability is null, not zero, when nothing was checked

The aggregate is the share of *checked* claims that were supported. With nothing
checked it is `None`. `0%` would assert that every claim failed; `100%` would
assert that all passed.

*Defended by:* `test_verification.py::test_reliability_is_none_when_nothing_was_checked`.

### I6 — Correction never destroys history

Applying a correction creates a **new** chunk and provenance row, links
`revision_of`, marks the original `superseded`, and points it forward with
`superseded_by`. The original row and its text are untouched, so every earlier
citation still resolves to what it actually said when it was made.

*Defended by:* `tests/integration/test_correction_lifecycle.py` against real
PostgreSQL, which asserts the original text survives and still resolves.

### I7 — Nobody approves their own correction

Enforced in the service (`ForbiddenError`) **and** by the
`corrections_validate_review` trigger. Service-level checks can be bypassed by a
future code path; a database constraint cannot.

*Defended by:* `test_verification.py::test_proposer_cannot_review_their_own_correction`
and the verifier's `self-approval refused` check using the real trigger.

### I8 — An agent cannot do its own work twice

The analyst cannot verify, and the critic cannot write or amend. See
[ADR-0013](adr/0013-agent-capability-isolation.md).

*Defended by:* `test_orchestration.py` capability tests.

### I9 — A skipped check is never recorded as a success

An answer whose critic did not run is returned with `degraded: true` and the
reason. An answer that asserts claims and was never checked is degraded too —
even when the plan deliberately omitted the critic for lack of a verification
model. "Unchecked" must not read as "checked and fine".

*Defended by:* `test_orchestration.py::test_a_skipped_critic_marks_the_answer_degraded`.

### I10 — Traces are written by the code that did the work

A step row is written after the work completes. The plan is written before
execution so a deviation is visible. Clients cannot write traces at all.

*Defended by:* `test_orchestration.py` (step ordering, plan-before-work) and
migration checks asserting `authenticated` has no INSERT on the trace tables.

## Hybrid retrieval in detail

Two rankers, fused:

| Signal | Source | Cost | Catches |
|---|---|---|---|
| Lexical | Postgres full-text (`ts_rank_cd`) | free | exact terms, names, numbers |
| Semantic | pgvector cosine over `chunk_embeddings` | one embedding call per query | paraphrase, synonyms |

Fusion is a weighted combination of the two ranks, with weights in configuration
(`RETRIEVAL_*` settings) rather than in code. Every result reports `matched_by`
(`lexical` / `semantic` / `both`) so a reader can see why a passage appeared.

**Honest degradation.** With no embedding provider configured, retrieval is
lexical-only and the response says so. It does not label lexical results
"hybrid" and does not silently return fewer results pretending to be the same
thing.

**Superseded evidence is excluded by default.** `include_superseded=true` is an
explicit request, which is why the flag exists: a user asking about a past policy
may genuinely want the old text, but they should have to ask.

## What is deliberately absent

- **No query rewriting.** The question is embedded as asked. Rewriting costs a
  model call and changes what the user asked; if it helps, that is a hypothesis
  for 4A to measure, not an assumption to bake in.
- **No reranker.** A cross-encoder reranker would improve ordering and cost
  another model call per question. Deferred to 4A, where the improvement can be
  measured rather than assumed.
- **No conversation memory in retrieval.** Follow-up questions do not rewrite the
  query using earlier turns, so "what about the second one?" retrieves poorly.
  This is a real limitation, stated here rather than hidden.
- **No cross-workspace retrieval.** Ever. Scope is the workspace, enforced by RLS
  and by `SECURITY INVOKER` functions.

## Verification in practice

Verification is not a gate on generation; it is an annotation on the result.
An answer with unsupported claims is still returned, with those claims marked, so
a user can see what the system says and what it can defend. Blocking answers at
generation time would hide the distinction between "wrong" and "unverifiable",
which is the distinction the thesis is about.

## Measuring any of this

None of the statements above are claims about quality. Thresholds are judgements
(see [ADR-0012](adr/0012-verification-policy.md)), not measurements. Phase 4A
exists to replace judgement with evidence: a labelled query set, retrieval recall
and precision, answer faithfulness, abstention correctness, and a comparison
against a RAG baseline. Until then, no quality figure appears anywhere in this
repository, because none has been measured.
