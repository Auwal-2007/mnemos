"""Embedding adapter tests (Phase 2C).

No live provider call is made. A fake `httpx.AsyncClient` returns recorded
OpenAI-wire-format responses, so the adapter's batching, validation, retry and
failure classification are exercised deterministically.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.infrastructure.embeddings import (
    EmbeddingDimensionMismatch,
    EmbeddingError,
    EmbeddingNotConfiguredError,
    OpenAICompatibleEmbeddingProvider,
    embedding_provider_from_settings,
)

MODEL = "test/embedding-model"
DIM = 4


def vector(value: float = 0.1) -> list[float]:
    return [value] * DIM


def response_for(inputs: list[str], dim: int = DIM, status: int = 200) -> httpx.Response:
    body = {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": [0.1] * dim}
            for index in range(len(inputs))
        ],
        "model": MODEL,
        "usage": {"prompt_tokens": 7 * len(inputs), "total_tokens": 7 * len(inputs)},
    }
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://x"))


class FakeClient:
    """Returns queued responses (or raises queued exceptions) in order."""

    def __init__(self, queue: list[Any]) -> None:
        self.queue = queue
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, json: Any = None, headers: Any = None) -> httpx.Response:
        self.calls.append({"url": url, "json": json, "headers": headers})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self) -> None:
        return None


def provider(client: FakeClient, **overrides: Any) -> OpenAICompatibleEmbeddingProvider:
    params: dict[str, Any] = {
        "base_url": "https://openrouter.ai/api/v1/embeddings",
        "api_key": "test-key",
        "model_id": MODEL,
        "dimension": DIM,
        "batch_size": 2,
        "max_retries": 2,
        "client": client,  # type: ignore[arg-type]
    }
    params.update(overrides)
    return OpenAICompatibleEmbeddingProvider(**params)


# --- request shape -------------------------------------------------------


async def test_posts_to_the_embeddings_endpoint_with_model_and_input() -> None:
    client = FakeClient([response_for(["a", "b"])])
    batch = await provider(client).embed(["a", "b"])

    assert client.calls[0]["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert client.calls[0]["json"] == {"model": MODEL, "input": ["a", "b"]}
    assert client.calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert len(batch.vectors) == 2
    assert batch.model == MODEL


async def test_chat_endpoint_is_refused() -> None:
    """An embedding payload must never be posted to a chat endpoint."""
    with pytest.raises(EmbeddingError) as error:
        provider(FakeClient([]), base_url="https://openrouter.ai/api/v1/chat/completions")
    assert "chat" in error.value.message.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1/chat/completions",
        "https://openrouter.ai/api/v1/completions",
    ],
)
async def test_completion_paths_are_refused(url: str) -> None:
    with pytest.raises(EmbeddingError):
        provider(FakeClient([]), base_url=url)


# --- batching ------------------------------------------------------------


async def test_respects_the_batch_size() -> None:
    client = FakeClient([response_for(["a", "b"]), response_for(["c"])])
    batch = await provider(client).embed(["a", "b", "c"])
    assert len(client.calls) == 2
    assert client.calls[0]["json"]["input"] == ["a", "b"]
    assert client.calls[1]["json"]["input"] == ["c"]
    assert len(batch.vectors) == 3


async def test_vectors_are_returned_in_input_order() -> None:
    client = FakeClient([response_for(["a", "b"])])
    batch = await provider(client).embed(["a", "b"])
    assert [vector.index for vector in batch.vectors] == [0, 1]


async def test_empty_input_makes_no_request() -> None:
    client = FakeClient([])
    batch = await provider(client).embed([])
    assert batch.vectors == []
    assert client.calls == []


async def test_usage_is_captured() -> None:
    client = FakeClient([response_for(["a", "b"])])
    batch = await provider(client).embed(["a", "b"])
    assert batch.prompt_tokens == 14


# --- dimension validation ------------------------------------------------


async def test_dimension_mismatch_is_rejected() -> None:
    client = FakeClient([response_for(["a"], dim=8)])
    with pytest.raises(EmbeddingDimensionMismatch) as error:
        await provider(client).embed(["a"])
    assert error.value.details == {"expected": DIM, "received": 8, "model": MODEL}


async def test_wrong_vector_count_is_rejected() -> None:
    body = {"data": [{"index": 0, "embedding": vector()}], "model": MODEL}
    client = FakeClient([httpx.Response(200, json=body, request=httpx.Request("POST", "u"))])
    with pytest.raises(EmbeddingError) as error:
        await provider(client).embed(["a", "b"])
    assert "number of vectors" in error.value.message


async def test_empty_vector_is_rejected() -> None:
    body = {"data": [{"index": 0, "embedding": []}], "model": MODEL}
    client = FakeClient([httpx.Response(200, json=body, request=httpx.Request("POST", "u"))])
    with pytest.raises(EmbeddingError):
        await provider(client).embed(["a"])


# --- retries and failures ------------------------------------------------


async def test_retries_on_429_then_succeeds() -> None:
    client = FakeClient(
        [
            httpx.Response(429, json={"error": "rate limit"}, request=httpx.Request("POST", "u")),
            response_for(["a"]),
        ]
    )
    batch = await provider(client).embed(["a"])
    assert len(client.calls) == 2
    assert batch.attempts == 2
    assert len(batch.vectors) == 1


async def test_retries_on_timeout_then_succeeds() -> None:
    client = FakeClient(
        [
            httpx.TimeoutException("slow"),
            response_for(["a"]),
        ]
    )
    batch = await provider(client).embed(["a"])
    assert len(batch.vectors) == 1


async def test_gives_up_after_bounded_retries() -> None:
    client = FakeClient(
        [
            httpx.Response(503, json={}, request=httpx.Request("POST", "u")),
            httpx.Response(503, json={}, request=httpx.Request("POST", "u")),
        ]
    )
    with pytest.raises(EmbeddingError) as error:
        await provider(client, max_retries=2).embed(["a"])
    assert "did not respond" in error.value.message or "unavailable" in error.value.message


async def test_non_retryable_4xx_fails_immediately() -> None:
    client = FakeClient(
        [httpx.Response(400, json={"error": "bad"}, request=httpx.Request("POST", "u"))]
    )
    with pytest.raises(EmbeddingError) as error:
        await provider(client).embed(["a"])
    assert "rejected" in error.value.message
    assert len(client.calls) == 1  # not retried


async def test_non_json_response_is_rejected() -> None:
    client = FakeClient([httpx.Response(200, text="<html>", request=httpx.Request("POST", "u"))])
    with pytest.raises(EmbeddingError) as error:
        await provider(client).embed(["a"])
    assert "non-JSON" in error.value.message


# --- configuration -------------------------------------------------------


def test_missing_key_is_not_configured() -> None:
    with pytest.raises(EmbeddingNotConfiguredError):
        provider(FakeClient([]), api_key="")


def test_missing_model_is_not_configured() -> None:
    with pytest.raises(EmbeddingNotConfiguredError):
        provider(FakeClient([]), model_id="")


def test_non_positive_dimension_is_not_configured() -> None:
    with pytest.raises(EmbeddingNotConfiguredError):
        provider(FakeClient([]), dimension=0)


def test_settings_factory_requires_configuration() -> None:
    settings = Settings(embedding_api_key="", embedding_model="")
    assert settings.is_embedding_configured is False
    with pytest.raises(EmbeddingNotConfiguredError):
        embedding_provider_from_settings(settings)


def test_settings_factory_builds_a_provider() -> None:
    settings = Settings(
        embedding_api_key="real-looking-key",
        embedding_model=MODEL,
        embedding_dimension=1024,
        embedding_base_url="https://openrouter.ai/api/v1/embeddings",
    )
    assert settings.is_embedding_configured is True
    built = embedding_provider_from_settings(settings)
    assert built.dimension == 1024
    assert built.model_id == MODEL


def test_default_endpoint_is_the_embeddings_path() -> None:
    settings = Settings()
    assert settings.embedding_base_url.endswith("/embeddings")
    assert "chat" not in settings.embedding_base_url
