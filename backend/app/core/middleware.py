"""HTTP middleware: request correlation identifiers and rate limiting."""

from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id to every request and echo it in responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        # Only accept a client-supplied id if it is a plausible opaque token.
        request_id = incoming[:64] if incoming and _is_safe(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _is_safe(value: str) -> bool:
    return all(ch.isalnum() or ch in "-_" for ch in value)


# ---------------------------------------------------------------------------
# Rate limiting
#
# Why this exists
# ---------------
# Every expensive route here spends a model call, an embedding call, or a
# database round trip on a caller's behalf. Authenticated users are identified by
# their verified token subject; anonymous callers by client address. Without a
# limit, one client can exhaust a workspace's budget or a provider's quota, and
# neither failure is visible to the other users who then cannot work.
#
# Honest limitation
# -----------------
# The counter is in-process. Behind multiple workers each holds its own budget,
# so the effective limit is (limit x workers), and a restart resets it. That is
# enough to stop a single runaway client, which is the realistic abuse here, and
# it adds no dependency. A distributed limiter belongs at the edge (proxy or
# gateway) and is noted as such in docs/SECURITY.md rather than pretended here.
# ---------------------------------------------------------------------------


@dataclass
class _Window:
    """Requests seen in the current interval."""

    count: int = 0
    reset_at: float = 0.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-caller request limiting.

    A fixed window is chosen over a sliding log because it costs O(1) memory per
    caller and its worst case — a burst straddling the boundary — is acceptable
    for abuse prevention, which is the goal. It is not a fairness mechanism.
    """

    def __init__(
        self,
        app: Any,
        *,
        limit: int = 120,
        window_seconds: float = 60.0,
        exempt_paths: tuple[str, ...] = ("/api/v1/health", "/api/v1/ready", "/health", "/ready"),
    ) -> None:
        super().__init__(app)
        self._limit = limit
        self._window = window_seconds
        self._exempt = exempt_paths
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def _caller(self, request: Request) -> str:
        """Identify the caller.

        The subject claim is preferred over the address because a shared NAT
        would otherwise make every user behind it share one budget. The claim is
        read without verifying the signature: it only groups requests that
        already passed authentication, and a forged claim can at worst pick a
        different bucket, which grants no access.
        """
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            parts = token.split(".")
            if len(parts) == 3:
                try:
                    payload = json.loads(_b64url_decode(parts[1]))
                    subject = payload.get("sub")
                    if isinstance(subject, str) and subject:
                        return f"sub:{subject}"
                except (ValueError, TypeError, KeyError):
                    pass
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if any(path == exempt or path.startswith(exempt + "/") for exempt in self._exempt):
            return await call_next(request)

        caller = self._caller(request)
        now = time.monotonic()
        with self._lock:
            window = self._windows.get(caller)
            if window is None or now >= window.reset_at:
                window = _Window(count=1, reset_at=now + self._window)
                self._windows[caller] = window
                allowed = True
            else:
                allowed = window.count < self._limit
                if allowed:
                    window.count += 1
            retry_after = max(0.0, window.reset_at - now)

            # Bound memory: an unbounded table keyed by caller is itself a
            # denial-of-service vector.
            if len(self._windows) > 10_000:
                self._windows = {
                    key: value for key, value in self._windows.items() if now < value.reset_at
                }

        if not allowed:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please slow down and try again.",
                        "request_id": getattr(request.state, "request_id", ""),
                        "details": {"retry_after_seconds": round(retry_after, 1)},
                    }
                },
                headers={"Retry-After": str(max(1, int(retry_after + 0.5)))},
            )

        return await call_next(request)


def _b64url_decode(segment: str) -> str:
    """Decode a base64url JWT segment without validating it."""
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", "replace")
