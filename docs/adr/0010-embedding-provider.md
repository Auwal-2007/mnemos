# ADR-0010: Embedding provider separated from the chat provider

- **Status:** Accepted (provider path verified by documentation; live call not made)
- **Date:** 2026-11-15
- **Supersedes:** the "embeddings generated via the OpenRouter adapter" clause of
  ADR-0006, which conflated the two concerns.

## Context

ADR-0004 designates OpenRouter as the model-access layer, and ADR-0006 proposed
generating embeddings "via the OpenRouter adapter". Investigation during Phase
2C found three facts that make that phrasing unsafe as an implementation rule:

1. **Embeddings use a different endpoint.** OpenRouter serves embeddings at
   `POST /api/v1/embeddings`, in the OpenAI wire format — *not* through
   `/chat/completions`. Posting an embedding payload to a chat endpoint is a
   category error that a provider may accept and answer nonsensically.
2. **Embeddings are absent from the model catalogue.** OpenRouter's `/v1/models`
   response contains no embedding models, which is why "OpenRouter has no
   embeddings" is a widespread belief. The models are served but not listed.
3. **The dimension is model-specific and must be known before the column is
   created.** `pgvector` types the column as `vector(N)`; a mismatch is a hard
   error, by design.

Everything above is documented by OpenRouter, not observed here: there is no
API key in this environment, so **no embedding request was made**.

## Decision

Treat embedding generation as its own provider concern, isolated behind an
adapter, with its own configuration:

| Setting | Purpose | Default |
|---|---|---|
| `EMBEDDING_BASE_URL` | full URL of an embeddings endpoint | `https://openrouter.ai/api/v1/embeddings` |
| `EMBEDDING_API_KEY` | provider credential | none |
| `EMBEDDING_MODEL` | model id | none |
| `EMBEDDING_DIMENSION` | expected vector size | `1536` |
| `EMBEDDING_BATCH_SIZE` | inputs per request | `32` |
| `EMBEDDING_TIMEOUT_SECONDS` | per-request timeout | `30` |
| `EMBEDDING_MAX_RETRIES` | bounded retries | `3` |

The adapter (`app/infrastructure/embeddings.py`) enforces:

- **no chat endpoint.** Any base URL containing `chat/completions` or
  `/completions` is rejected at construction, so a misconfiguration cannot send
  vectors to a chat path;
- **dimension validation.** Every returned vector is checked against
  `EMBEDDING_DIMENSION`; a mismatch raises `EmbeddingDimensionMismatch` and
  nothing is stored;
- **bounded retries** on 429/5xx/timeouts with exponential backoff; other 4xx
  fail immediately (not retryable);
- **usage capture** (`prompt_tokens`) for cost accounting, recorded per run.

The database column's dimension comes from the same setting at migration time
(`app.embedding_dimension`), so the index cannot be created at a dimension the
application does not expect.

## Alternatives considered

- **Reuse the chat client for embeddings.** Rejected: identical transport does
  not mean identical endpoint or payload; the isolation is what prevents the
  class of bug above.
- **Hardcode a dimension (e.g. 1536).** Rejected: it silently couples the schema
  to one model. It is a default, overridable, and validated.
- **A dedicated vector database.** Rejected for now, as in ADR-0006: a second
  system adds consistency risk without a demonstrated need at this scale.
- **Local sentence-transformers.** Rejected for this phase: adds a large
  dependency and a model download, and the project's inference gateway decision
  (ADR-0004) points at a hosted provider.

## Consequences

- Positive: the schema, the adapter and the configuration agree on one
  dimension; a provider swap touches one module; a chat misconfiguration cannot
  corrupt the index.
- Negative: an extra set of environment variables; the operator must know the
  dimension their chosen model returns.
- **Unverified:** no live embedding call, therefore no confirmed dimension for
  any specific model. The verification step is documented in
  `docs/RETRIEVAL_DESIGN.md` and `DEPLOYMENT_GUIDE.md`; the code reports a
  mismatch loudly rather than silently adapting.
