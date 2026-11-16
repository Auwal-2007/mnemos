# ADR-0012: Verification policy — method, thresholds and failure behaviour

- **Status:** Accepted
- **Date:** 2026-11-15
- **Relates to:** FR-007, FR-008, FR-009, FR-012; ADR-0004 (OpenRouter); ADR-0005 (repository architecture)

## Context

Phase 3C must answer a question the product cannot avoid: **how does the system
know whether a generated claim is supported by the evidence it cites?** Three
answers were available, and they differ in cost, determinism and honesty.

1. **Trust the model.** Ask it to mark its own claims. Cheap, but it is
   self-assessment, and self-assessment cannot distinguish a well-supported
   claim from a confidently worded one. A critic that grades its own work is not
   a critic.
2. **Lexical overlap only.** Deterministic, free and explainable: how much of a
   claim's vocabulary appears in the cited passage. It cannot detect a
   *contradiction* — "valid for six months" and "valid for three months" share
   almost every word — and it can be fooled by paraphrase.
3. **A second model call, given the claim and its evidence.** Catches
   contradiction and paraphrase, but introduces cost, latency and a new failure
   mode: the verifier itself can be wrong, unavailable, or return nonsense.

None of the three is sufficient alone, and the wrong choice is silent. A
verifier that overstates support is worse than no verifier, because it converts
an unchecked answer into an apparently checked one.

## Decision

**Two methods, both recorded with every verdict, and a failure policy that never
turns uncertainty into support.**

### Methods

- `lexical_overlap` — deterministic, cost-free, always available. Computed as the
  share of the claim's content words (stop-words removed) present in the cited
  evidence, with the contributing chunk ids recorded.
- `model_judgement` — a second completion call given the claim and the evidence
  passages, returning a structured verdict with confidence and an explanation.
  Available only when a verification model is configured.
- `manual` is reserved in the enum for a human verdict and is not yet produced by
  any code path. It is declared so the database does not need a migration when it
  is added, not because it works today.

Every stored verdict records which method produced it. A reader can therefore
tell a cheap check from an expensive one.

### Thresholds (lexical)

| Score | Verdict | Reasoning |
|---|---|---|
| ≥ 0.70 | `supported` | Most of the claim's vocabulary is in the cited passage. |
| 0.45 – 0.70 | `partially_supported` | Some support, not enough to assert. Treated as *not* supported. |
| < 0.45 | `unsupported` | The claim and the passage do not share enough vocabulary. |

The gap between 0.45 and 0.70 is deliberately wide. A narrow band would
manufacture false confidence: lexical scoring is a proxy, and a proxy should not
claim precision it does not have.

### `unverified` is not `unsupported`

Absence of a verdict means **nobody checked**. `unsupported` means **somebody
checked and the evidence did not support it**. These are different facts and the
system never merges them:

- a claim with no resolvable cited evidence stays `unverified`;
- a provider error during `model_judgement` leaves claims `unverified`;
- unusable model output leaves claims `unverified`.

### Reliability

`reliability` is the share of *checked* claims that were supported, and it is
**null when nothing was checked**. Reporting 0% would state that every claim
failed; reporting 100% would state that all of them passed. Both would be
fabrications, and the null is visible in the API rather than merely in a comment.

### Failure behaviour

`model_judgement` **fails closed**. Any of the following leaves the claim
unverified rather than supported: transport failure, non-JSON response, missing
required fields, or a verdict outside the permitted set.

## Consequences

**Good**

- The default path costs nothing and cannot be rate-limited.
- Contradiction detection is possible when a model is available, and impossible
  work is not claimed when it is not.
- Every aggregate number traces back to individual verdicts with a stated method.
- A verifier outage degrades the product to lexical checking; it does not corrupt
  stored state.

**Costs and limits**

- Lexical scoring will mark a correct paraphrase `partially_supported`. This is
  accepted: a false negative is recoverable by a human reviewer, a false positive
  is not.
- Two methods mean two code paths to test, and the model path has only ever been
  exercised against a mock provider in this repository.
- The thresholds are a judgement, not a measurement. They are named constants in
  one module so that Phase 4A can calibrate them against a labelled set, and so
  that any change is visible in a diff rather than buried in a formula.

## Alternatives rejected

**Model-only verification.** Rejected: it makes correctness depend on a paid
provider being available, and it removes the ability to check anything without
spending money.

**Lexical-only.** Rejected: it cannot detect contradiction, which is precisely
what FR-008 asks for.

**Third-party evaluation framework.** Rejected for now: it would introduce a
dependency whose scoring is not inspectable in this codebase, and Phase 4A is the
right place to compare our numbers against an external baseline.
