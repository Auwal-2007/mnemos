# ADR-0013: Agent capability isolation and trace fidelity

- **Status:** Accepted
- **Date:** 2026-11-15
- **Relates to:** FR-001, FR-002, FR-014, NFR-013; ADR-0012 (verification policy)

## Context

Phase 3D introduces four agents. "Agent" is an overloaded word, and the two
common meanings push the design in opposite directions.

The **autonomous-agent** meaning is a loop: a model chooses tools, observes
results, and decides what to do next, possibly many times. It demoes well. It is
also unreproducible (the same question can take different paths), unbounded in
cost, and — decisively for this project — **unauditable**. A trace produced by a
system that chose its own steps records what it decided to report, which is not
the same as what it did.

The **role** meaning is a fixed specialisation: a named responsibility, a
declared capability set, and a recorded outcome. Less impressive; far more
checkable.

The project's own constraints decide this. FR-014 requires execution metadata
that a reader can trust, the approved methodology requires reproducible
evaluation in Phase 4A, and the standing instruction is that no fake
implementation or invented response is permitted. An autonomous loop makes all
three harder, and buys nothing the thesis needs to demonstrate.

## Decision

**Agents are roles with declared capabilities, not autonomous loops.**

### Capability isolation

| Role | May do | May not do |
|---|---|---|
| `orchestrator` | choose the plan, write the trace | produce or alter answer text |
| `researcher` | retrieve evidence | generate or verify |
| `analyst` | generate a grounded answer | retrieve (beyond what it was given), verify |
| `critic` | verify against the given evidence | generate, amend the answer, retrieve fresh evidence |

Three mechanisms enforce this, in order of strength:

1. **Construction.** Each agent receives only the services its capabilities
   allow. The analyst is not handed a verifier; the critic is not handed a
   generator. A capability that was never injected cannot be called.
2. **A seam guard.** `require_capability()` is called before the work, so if
   wiring drifts the call fails with a named error instead of quietly succeeding.
3. **No general capability exists.** There is no `execute_sql`, no `write_file`,
   no arbitrary HTTP tool, and no configuration flag that adds one (NFR-013). The
   system cannot be extended into an agent that runs SQL by editing settings.

### Trace fidelity

- A step row is written **after** the work it describes, by the code that did it.
- The plan is recorded **before** execution, so the trace can contradict the plan
  and that contradiction is visible.
- `skipped` is a distinct status from `succeeded` and carries its reason. An
  answer whose critic was skipped is returned with `degraded: true`.
- A failed analyst writes no answer row and no success claim.
- Traces carry results (counts, verdicts, statuses), never document text or raw
  prompts — the corpus is not duplicated into the trace tables.
- Traces are written server-side only. `authenticated` holds SELECT and
  deliberately no INSERT: a trace a client can author is not evidence.

### Determinism where it counts

The plan's only branch is whether a critic runs, and that follows configuration.
Asking a model which agents to use would make the trace a claim about a decision
rather than a record of one, and would make 4A's comparisons non-reproducible.

## Consequences

**Good**

- Every orchestration is explainable row by row, and the explanation is written
  by the code that did the work.
- Cost and latency are bounded and predictable: one generation call, optionally
  one verification call.
- Phase 4A can compare runs because the pipeline is the same each time.
- The separation of duties from 3C extends naturally: the analyst cannot verify
  its own answer any more than a correction's proposer can approve it.

**Costs and limits**

- The system cannot discover a novel strategy. That is a real ceiling, accepted
  deliberately.
- Four roles over three services is more moving parts than one service call; the
  orchestration tests exist to keep that honest.
- The critic is skipped when no verification model is configured, so the
  strongest configuration's behaviour is the one least exercised here: the model
  path has never run against a live provider in this repository.

## Alternatives rejected

**Free-running tool-using agents.** Rejected: unverifiable trace, unbounded cost,
non-reproducible evaluation.

**A single "agent" object with role as a field.** Rejected: it makes capability
isolation a runtime check on a string rather than a structural property, and the
check would eventually be forgotten.

**Storing traces only in logs.** Rejected: FR-014 requires queryable execution
metadata, and a log line cannot be joined to an answer or shown to a user.
