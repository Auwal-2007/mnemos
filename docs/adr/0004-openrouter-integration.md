# ADR-0004: OpenRouter integration approach

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

MNEMOS needs configurable AI model access for multiple agent
responsibilities (orchestrator, retrieval, memory, verification) without
hardcoding model identifiers or assuming uniform model capabilities.
OpenRouter provides a single routing layer over many models.

## Decision

Use OpenRouter as the model-access and routing layer (not as a model).
Access is centralized in a single adapter with environment-based API
keys, per-responsibility model IDs from environment variables, request/
response normalization, structured-output validation, tool-calling
capability checks, timeouts, bounded retries, error classification,
rate-limit handling, and usage/cost logging. Model IDs are recorded in
every execution record. No paid calls without explicit approval. Phase 0
prepares the boundary and configuration only — no adapter code and no
model calls.

## Alternatives considered

- **Direct provider APIs (OpenAI, Anthropic, etc.):** rejected — couples
  the application to specific providers and complicates model switching;
  OpenRouter provides a unified interface.
- **Hardcoded single model:** rejected — violates replaceability and
  per-responsibility configuration requirements (NFR-008).
- **Local/self-hosted models:** rejected — operational burden and
  capability gaps for this project's scope.

## Consequences

- Positive: model replaceability, unified interface, per-agent
  configuration, usage/cost visibility.
- Negative: dependency on OpenRouter availability and pricing; model
  capability variance requires per-model validation (structured output,
  tool calling).
- Follow-up: validate candidate models per responsibility in the AI
  integration phase; implement the adapter with tests using fixtures,
  never live paid calls in CI.
