"""Embedding provider adapter (Phase 2C).

Provider decision
-----------------
OpenRouter documents a dedicated **`POST /api/v1/embeddings`** endpoint that
returns vectors in the OpenAI wire format. It is *not* the chat-completions
endpoint, and embeddings are deliberately absent from OpenRouter's `/models`
catalogue, which is why "OpenRouter has no embedding models" is a common and
now-outdated belief.

The adapter therefore treats the embedding provider as a **separate concern**
from the chat provider even when they share a URL and key:

* the endpoint path is its own setting (`EMBEDDING_BASE_URL`), defaulting to the
  OpenRouter embeddings path and never to a chat path;
* a guard rejects any base URL that contains `chat/completions`, so a
  misconfiguration cannot send embedding payloads to a chat endpoint;
* the model id, dimension and batch size are configuration, not constants;
* the reported dimension is **checked against** the configured dimension and a
  mismatch is an error, never a silent resize.

If a different embeddings provider is needed (OpenAI directly, a local
sentence-transformers server, Voyage, Cohere), only this module changes: the
pipeline consumes the `EmbeddingProvider` protocol.

Honesty about verification
--------------------------
No embedding request has been made in this environment: there is no API key.
The request/response shapes follow the documented OpenAI-compatible contract
and are covered by tests with recorded fixtures. The **real dimension of a
given model must be confirmed** in the target deployment — the tests assert
that a mismatch is rejected rather than trusted.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import MnemosError

logger = logging.getLogger("mnemos.embeddings")

#: Embedding payloads must never be posted to a chat endpoint.
_FORBIDDEN_PATH_FRAGMENTS = ("chat/completions", "chat/completion", "/completions")


class EmbeddingError(MnemosError):
    """An embedding request failed."""

    status_code = 502
    code = "embedding_failed"
    default_message = "The embedding provider could not process this text."


class EmbeddingNotConfiguredError(MnemosError):
    """No embedding provider is configured."""

    status_code = 503
    code = "embedding_not_configured"
    default_message = (
        "Embeddings are not configured. Set EMBEDDING_API_KEY, EMBEDDING_MODEL "
        "and EMBEDDING_DIMENSION to enable indexing."
    )


class EmbeddingDimensionMismatch(EmbeddingError):
    """The provider returned a different dimension than the schema expects."""

    code = "embedding_dimension_mismatch"
    default_message = (
        "The embedding model returned a different vector size than the database "
        "is configured for. Re-index with a matching model or dimension."
    )


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """One vector plus the model that produced it."""

    index: int
    values: list[float]


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """The result of embedding a batch, with usage for cost accounting."""

    vectors: list[EmbeddingVector]
    model: str
    prompt_tokens: int | None = None
    latency_ms: int = 0
    attempts: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


class EmbeddingProvider(Protocol):
    """What the indexing pipeline needs from an embedding provider."""

    @property
    def dimension(self) -> int: ...

    @property
    def model_id(self) -> str: ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch: ...


def _validate_base_url(url: str) -> None:
    lowered = url.lower()
    for fragment in _FORBIDDEN_PATH_FRAGMENTS:
        if fragment in lowered:
            raise EmbeddingError(
                message=(
                    "The embedding endpoint is configured to a chat-completion "
                    "path. Embeddings must use the provider's embeddings endpoint."
                )
            )


class OpenAICompatibleEmbeddingProvider:
    """An OpenAI-wire-format embeddings client (OpenRouter, OpenAI, others).

    Batching, retry with exponential backoff on retryable failures, dimension
    validation and usage capture all happen here so no caller has to think
    about them.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        dimension: int,
        batch_size: int = 32,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise EmbeddingNotConfiguredError()
        if not model_id:
            raise EmbeddingNotConfiguredError(
                message="EMBEDDING_MODEL is not set. Set it to a model the provider serves."
            )
        if dimension <= 0:
            raise EmbeddingNotConfiguredError(
                message="EMBEDDING_DIMENSION must be a positive integer."
            )
        _validate_base_url(base_url)

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_id = model_id
        self._dimension = dimension
        self._batch_size = max(1, batch_size)
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)
        self._client = client
        self._owns_client = client is None

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed ``texts`` in batches; return vectors in input order."""
        if not texts:
            return EmbeddingBatch(vectors=[], model=self._model_id)

        vectors: list[EmbeddingVector] = []
        prompt_tokens = 0
        attempts = 1
        started = time.monotonic()

        for offset in range(0, len(texts), self._batch_size):
            batch = list(texts[offset : offset + self._batch_size])
            payload, used_attempts = await self._post_with_retry(batch)
            attempts = max(attempts, used_attempts)

            data = payload.get("data")
            if not isinstance(data, list) or len(data) != len(batch):
                raise EmbeddingError(
                    message="The embedding provider returned an unexpected number of vectors."
                )

            # Usage is reported once per request, not per item.
            prompt_tokens += _usage_tokens(payload)
            for item in data:
                if not isinstance(item, dict):
                    raise EmbeddingError(message="The embedding provider returned malformed data.")
                embedding = item.get("embedding")
                if not isinstance(embedding, list) or not embedding:
                    raise EmbeddingError(message="The embedding provider returned an empty vector.")
                if len(embedding) != self._dimension:
                    raise EmbeddingDimensionMismatch(
                        message=(
                            f"The embedding model returned {len(embedding)} dimensions "
                            f"but the index expects {self._dimension}."
                        ),
                        details={
                            "expected": self._dimension,
                            "received": len(embedding),
                            "model": self._model_id,
                        },
                    )
                index = item.get("index")
                vectors.append(
                    EmbeddingVector(
                        index=int(index) if isinstance(index, int) else len(vectors),
                        values=[float(value) for value in embedding],
                    )
                )

        # Providers may return items out of order; sort by the reported index.
        vectors.sort(key=lambda vector: vector.index)
        return EmbeddingBatch(
            vectors=vectors,
            model=self._model_id,
            prompt_tokens=prompt_tokens or None,
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=attempts,
            metadata={"batch_size": self._batch_size},
        )

    async def _post_with_retry(self, batch: list[str]) -> tuple[dict[str, Any], int]:
        payload = {"model": self._model_id, "input": batch}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._request(payload, headers)
            except httpx.TimeoutException as exc:
                last_error = exc
                await asyncio.sleep(min(2**attempt * 0.25, 4.0))
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(min(2**attempt * 0.25, 4.0))
                continue

            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = EmbeddingError(
                    message="The embedding provider is rate-limiting or unavailable."
                )
                logger.warning(
                    "Embedding request retryable failure (status=%s attempt=%s)",
                    response.status_code,
                    attempt,
                )
                await asyncio.sleep(min(2**attempt * 0.25, 4.0))
                continue

            if response.status_code >= 400:
                # 4xx other than 429 is not retryable: the request is wrong.
                raise EmbeddingError(
                    message="The embedding provider rejected the request.",
                    details={"status": response.status_code},
                )

            try:
                parsed = response.json()
            except ValueError as exc:
                raise EmbeddingError(
                    message="The embedding provider returned a non-JSON response."
                ) from exc
            if not isinstance(parsed, dict):
                raise EmbeddingError(message="The embedding provider returned malformed data.")
            return parsed, attempt

        raise EmbeddingError(
            message="The embedding provider did not respond after several attempts.",
            details={"last_error": type(last_error).__name__ if last_error else None},
        )

    async def _request(self, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return await self._client.post(self._base_url, json=payload, headers=headers)


def _usage_tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage")
    if isinstance(usage, dict):
        value = usage.get("prompt_tokens") or usage.get("total_tokens")
        if isinstance(value, int):
            return value
    return 0


def embedding_provider_from_settings(settings: Settings) -> EmbeddingProvider:
    """Build the configured provider, or fail with an actionable message."""
    if not settings.is_embedding_configured:
        raise EmbeddingNotConfiguredError()
    return OpenAICompatibleEmbeddingProvider(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model_id=settings.embedding_model,
        dimension=settings.embedding_dimension,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
    )
