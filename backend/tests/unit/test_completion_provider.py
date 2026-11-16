"""Completion provider tests (owed since Phase 3B).

These exercise the real HTTP client against a mock transport, so the request the
provider builds and the response it parses are both verified without any network
call and without spending anything. That distinction matters: this file proves
the client is wired correctly; it does not and cannot prove a live model behaves
well. Model quality belongs to Phase 4A, and nothing here is a claim about it.

What is protected:

* the gateway URL, auth header and JSON body are what OpenRouter expects;
* a missing key fails at construction, not at the first user question;
* HTTP errors and transport errors surface as `CompletionError`, never as a
  silently empty answer;
* usage numbers are read from the response rather than invented;
* the model actually reported is captured separately from the one requested,
  because gateways silently substitute and the trace must not lie about it.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.infrastructure.completion import (
    ChatMessage,
    CompletionError,
    CompletionNotConfiguredError,
    OpenRouterChatProvider,
    chat_provider_from_settings,
)

BASE = "https://openrouter.example/api/v1"


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def provider(
    handler,
    *,
    model: str = "vendor/model-a",
    key: str = "test-key",
    max_retries: int = 1,
) -> OpenRouterChatProvider:
    """Provider over a mock transport.

    ``max_retries=1`` by default: retry behaviour is not what these tests are
    about, and the backoff sleeps would make the suite slow for no benefit. The
    retry test below raises it explicitly.
    """
    return OpenRouterChatProvider(
        api_key=key,
        model_id=model,
        base_url=BASE,
        client=client_for(handler),
        max_retries=max_retries,
    )


def success_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": "gen-1",
        "model": "vendor/model-a",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": '{"answer": "ok"}'},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }
    body.update(overrides)
    return body


MESSAGES = [
    ChatMessage(role="system", content="You answer from evidence."),
    ChatMessage(role="user", content="Do I need a passport?"),
]


async def test_request_goes_to_the_configured_gateway_with_a_bearer_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=success_body())

    result = await provider(handler).complete(MESSAGES, temperature=0.2, max_tokens=64)

    assert seen["url"] == f"{BASE}/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "vendor/model-a"
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == 64
    assert body["messages"] == [
        {"role": "system", "content": "You answer from evidence."},
        {"role": "user", "content": "Do I need a passport?"},
    ]
    assert result.content == '{"answer": "ok"}'


async def test_json_response_format_is_forwarded_when_requested() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=success_body())

    await provider(handler).complete(MESSAGES, response_format={"type": "json_object"})
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["response_format"] == {"type": "json_object"}


async def test_usage_is_read_from_the_response_not_invented() -> None:
    result = await provider(lambda request: httpx.Response(200, json=success_body())).complete(
        MESSAGES
    )
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (11, 7)
    assert result.usage.total_tokens == 18


async def test_missing_usage_is_reported_as_missing() -> None:
    """Absent usage must stay absent; zero would be a fabricated measurement."""
    body = success_body()
    del body["usage"]
    result = await provider(lambda request: httpx.Response(200, json=body)).complete(MESSAGES)
    assert result.usage.total_tokens is None


async def test_a_substituted_model_is_recorded_rather_than_hidden() -> None:
    body = success_body(model="vendor/model-b")
    result = await provider(lambda request: httpx.Response(200, json=body)).complete(MESSAGES)
    assert result.model_requested == "vendor/model-a"
    assert result.model_reported == "vendor/model-b"


async def test_an_error_status_raises_rather_than_returning_empty_content() -> None:
    with pytest.raises(CompletionError) as excinfo:
        await provider(
            lambda request: httpx.Response(429, json={"error": {"message": "rate limited"}})
        ).complete(MESSAGES)
    # Retries exhaust, then the caller is told the reason rather than only that
    # something failed.
    assert "rate-limit" in str(excinfo.value).lower()


async def test_a_transport_failure_raises_completion_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    with pytest.raises(CompletionError):
        await provider(handler).complete(MESSAGES)


async def test_a_malformed_body_raises_rather_than_looking_like_an_answer() -> None:
    with pytest.raises(CompletionError):
        await provider(lambda request: httpx.Response(200, json={"choices": []})).complete(MESSAGES)


async def test_an_empty_message_content_raises() -> None:
    body = success_body(
        choices=[
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ]
    )
    with pytest.raises(CompletionError):
        await provider(lambda request: httpx.Response(200, json=body)).complete(MESSAGES)


def test_a_missing_key_is_refused_at_construction() -> None:
    with pytest.raises(CompletionNotConfiguredError):
        OpenRouterChatProvider(api_key="", model_id="vendor/model-a", base_url=BASE)


def test_a_missing_model_is_refused_at_construction() -> None:
    with pytest.raises(CompletionNotConfiguredError):
        OpenRouterChatProvider(api_key="k", model_id="", base_url=BASE)


def test_settings_without_a_key_produce_no_provider() -> None:
    settings = Settings(openrouter_api_key="", environment="test")
    assert settings.is_openrouter_configured is False
    with pytest.raises(CompletionNotConfiguredError):
        chat_provider_from_settings(settings, role="generation")


def test_a_placeholder_key_is_not_treated_as_configured() -> None:
    """A copy-pasted template value must not look like a working key."""
    settings = Settings(openrouter_api_key="your-key-here", environment="test")
    assert settings.is_openrouter_configured is False


def test_no_model_id_is_hardcoded_in_the_provider_module() -> None:
    """Model choice belongs to configuration, not to source."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "app" / "infrastructure" / "completion.py"
    text = source.read_text(encoding="utf-8")
    for vendor_prefix in ("anthropic/", "openai/", "google/", "meta-llama/", "mistralai/"):
        assert vendor_prefix not in text, (
            f"hardcoded model id prefix {vendor_prefix!r} in {source.name}"
        )
