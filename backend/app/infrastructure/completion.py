"""Chat-completion adapter (Phase 3B).

Provider decision
-----------------
OpenRouter is the approved inference gateway (ADR-0006). This adapter speaks
OpenRouter's OpenAI-compatible `POST /chat/completions` API directly, which
means:

* the model id is always configuration (`OPENROUTER_*_MODEL`), never a constant
  in business logic (NFR-008);
* the response's *reported* model is recorded, not the requested one, so an
  execution record cannot claim a model that did not run (FR-014);
* a provider outage is a typed error, never a silent empty answer.

Separation from embeddings
--------------------------
Embeddings have their own adapter with its own base URL, because a chat request
must never be sent to the embeddings endpoint or vice versa. This module
refuses any base URL containing `embeddings` for the same reason.

Honesty about verification
--------------------------
No model call has been made in this environment: there is no API key, and the
project's rules forbid paid calls without approval. The wire format below
follows OpenRouter's documented OpenAI-compatible contract and is covered by
tests with recorded shapes. Every code path that would spend money is therefore
**unverified against the live service** and is labelled as such in the docs.

Prompt-injection stance
-----------------------
Retrieved document text is *data*, never instruction. The adapter cannot
enforce that on its own, so `app/services/generation.py` builds every prompt
with retrieved text inside an explicitly delimited, labelled block, and the
model is told that content inside it is untrusted. That is mitigation, not a
guarantee; Phase 6's threat model records the residual risk.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import MnemosError

logger = logging.getLogger("mnemos.completion")

#: A chat request must never be posted to an embeddings path.
_FORBIDDEN_PATH_FRAGMENTS = ("embeddings", "embed")


class CompletionError(MnemosError):
    """The model provider failed or returned something unusable."""

    status_code = 502
    code = "completion_failed"
    default_message = "The language model could not produce an answer."


class CompletionNotConfiguredError(MnemosError):
    """No chat provider/model is configured."""

    status_code = 503
    code = "completion_not_configured"
    default_message = (
        "Answer generation is not configured. Set OPENROUTER_API_KEY and the "
        "OPENROUTER_*_MODEL variables to enable it."
    )


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One turn sent to the model."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class CompletionUsage:
    """Token usage as reported by the provider. Absent values stay absent."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """A completed model call.

    `model_reported` is what the provider says it used. It is stored in the
    execution record so a router that silently substitutes a model is visible
    rather than invisible.
    """

    content: str
    model_requested: str
    model_reported: str | None
    usage: CompletionUsage
    latency_ms: int
    attempts: int = 1
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChatProvider(Protocol):
    """What the generation service needs from a model provider."""

    @property
    def model_id(self) -> str: ...

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult: ...


def _validate_base_url(url: str) -> None:
    lowered = url.lower()
    for fragment in _FORBIDDEN_PATH_FRAGMENTS:
        if fragment in lowered:
            raise CompletionError(
                message=(
                    "The chat endpoint is configured to an embeddings path. "
                    "Generation must use the chat-completions endpoint."
                )
            )


class OpenRouterChatProvider:
    """OpenAI-compatible chat client with retry, timeout and usage capture."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_id: str,
        timeout_seconds: float = 45.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
        app_url: str | None = None,
        app_name: str = "mnemos",
    ) -> None:
        if not api_key:
            raise CompletionNotConfiguredError()
        if not model_id.strip():
            raise CompletionNotConfiguredError(
                message="A model id is required. Set the OPENROUTER_*_MODEL variables."
            )
        _validate_base_url(base_url)

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_id = model_id.strip()
        self._timeout = timeout_seconds
        self._max_retries = max(1, max_retries)
        self._client = client
        self._owns_client = client is None
        # OpenRouter uses these for attribution; optional and non-secret.
        self._app_url = app_url
        self._app_name = app_name

    @property
    def model_id(self) -> str:
        return self._model_id

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._app_url:
            headers["HTTP-Referer"] = self._app_url
        headers["X-Title"] = self._app_name
        return headers

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        if not messages:
            raise CompletionError(message="A completion needs at least one message.")

        payload: dict[str, Any] = {
            "model": self._model_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        started = time.monotonic()
        body, attempts = await self._post_with_retry(payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        content, finish_reason = _extract_content(body)
        return CompletionResult(
            content=content,
            model_requested=self._model_id,
            model_reported=_reported_model(body),
            usage=_usage(body),
            latency_ms=latency_ms,
            attempts=attempts,
            finish_reason=finish_reason,
            metadata={"response_id": _response_id(body)},
        )

    async def _post_with_retry(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._request(payload)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                logger.warning("Completion transport failure (attempt=%s)", attempt)
                await asyncio.sleep(min(2**attempt * 0.25, 4.0))
                continue

            if response.status_code in {429, 500, 502, 503, 504}:
                # Keep the reason, not just the fact of failure: after the last
                # attempt the caller is told *why*, which is what a user needs to
                # act on. "Did not respond" alone is unactionable.
                if response.status_code == 429:
                    last_error = CompletionError(
                        message="The model provider is rate-limiting requests. Try again shortly.",
                        details={"status": 429},
                    )
                else:
                    last_error = CompletionError(
                        message=(
                            f"The model provider is unavailable (status {response.status_code}). "
                            "Try again shortly."
                        ),
                        details={"status": response.status_code},
                    )
                logger.warning(
                    "Completion retryable failure (status=%s attempt=%s)",
                    response.status_code,
                    attempt,
                )
                await asyncio.sleep(min(2**attempt * 0.25, 4.0))
                continue

            if response.status_code >= 400:
                raise CompletionError(
                    message="The model provider rejected the request.",
                    details={"status": response.status_code},
                )

            try:
                parsed = response.json()
            except ValueError as exc:
                raise CompletionError(
                    message="The model provider returned a non-JSON response."
                ) from exc
            if not isinstance(parsed, dict):
                raise CompletionError(message="The model provider returned malformed data.")
            return parsed, attempt

        if isinstance(last_error, CompletionError):
            raise last_error
        if last_error is not None:
            # A transport failure must surface as the domain error. Letting raw
            # httpx exceptions escape would make call sites catch a library type
            # they do not know about — and the API layer would return a 500
            # instead of an honest provider failure.
            raise CompletionError(
                message=(
                    "The model provider could not be reached. Check connectivity and try again."
                ),
                details={"transport_error": type(last_error).__name__},
            ) from last_error
        raise CompletionError(message="The model provider did not respond after several attempts.")

    async def _request(self, payload: dict[str, Any]) -> httpx.Response:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return await self._client.post(
            f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
        )


def _extract_content(body: dict[str, Any]) -> tuple[str, str | None]:
    """Pull the assistant text out of an OpenAI-compatible response."""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise CompletionError(message="The model provider returned no choices.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise CompletionError(message="The model provider returned a malformed choice.")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise CompletionError(message="The model provider returned no message.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise CompletionError(message="The model provider returned an empty answer.")
    finish = choice.get("finish_reason")
    return content, str(finish) if finish is not None else None


def _reported_model(body: dict[str, Any]) -> str | None:
    value = body.get("model")
    return str(value) if isinstance(value, str) and value.strip() else None


def _response_id(body: dict[str, Any]) -> str | None:
    value = body.get("id")
    return str(value) if isinstance(value, str) else None


def _usage(body: dict[str, Any]) -> CompletionUsage:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return CompletionUsage()

    def as_int(key: str) -> int | None:
        value = usage.get(key)
        return value if isinstance(value, int) and value >= 0 else None

    return CompletionUsage(
        prompt_tokens=as_int("prompt_tokens"),
        completion_tokens=as_int("completion_tokens"),
        total_tokens=as_int("total_tokens"),
    )


def chat_provider_from_settings(settings: Settings, *, role: str = "default") -> ChatProvider:
    """Build the configured chat provider for a role.

    Each role has its own model setting so retrieval, generation, verification
    and orchestration can use different models without touching code. A role
    with no specific model falls back to the default, and refusing to guess is
    deliberate: an unset model must never silently become a hardcoded one.
    """
    if not settings.is_openrouter_configured:
        raise CompletionNotConfiguredError()

    model = settings.model_for_role(role)
    if not model:
        raise CompletionNotConfiguredError(
            message=(
                f"No model is configured for role '{role}'. Set "
                f"OPENROUTER_{role.upper()}_MODEL or OPENROUTER_DEFAULT_MODEL."
            )
        )
    return OpenRouterChatProvider(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        model_id=model,
        timeout_seconds=settings.openrouter_timeout_seconds,
        max_retries=settings.openrouter_max_retries,
        app_name=settings.app_name,
    )


def dumps(value: Any) -> str:
    """Stable JSON for prompts and fingerprints."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
