"""Rate limiting (Phase 6A).

These tests exist because a limiter that is configured but never exercised is
indistinguishable from one that does not work. They assert both directions: the
limit is enforced, and the probes a load balancer depends on are never limited
(a rate-limited health check would mark a healthy instance as down).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware


def _token(subject: str) -> str:
    """Build an unsigned JWT-shaped token with the given subject."""

    def segment(payload: object) -> str:
        raw = json.dumps(payload).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{segment({'alg': 'none'})}.{segment({'sub': subject})}.signature"


@pytest.fixture
def limited() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit=3, window_seconds=60.0)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/api/v1/thing")
    def thing() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        yield client


def test_requests_under_the_limit_succeed(limited: TestClient) -> None:
    for _ in range(3):
        assert limited.get("/api/v1/thing").status_code == 200


def test_the_limit_is_enforced(limited: TestClient) -> None:
    for _ in range(3):
        limited.get("/api/v1/thing")
    response = limited.get("/api/v1/thing")
    assert response.status_code == 429


def test_the_rejection_uses_the_standard_error_envelope(limited: TestClient) -> None:
    for _ in range(4):
        response = limited.get("/api/v1/thing")
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert "slow down" in body["error"]["message"]
    assert response.headers["Retry-After"].isdigit()


def test_health_probes_are_never_rate_limited(limited: TestClient) -> None:
    """A limited health check would cause an orchestrator to kill a live instance."""
    for _ in range(20):
        assert limited.get("/api/v1/health").status_code == 200


def test_callers_are_bucketed_by_token_subject_not_by_address() -> None:
    """Two users behind one NAT must not share a budget."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit=2, window_seconds=60.0)

    @app.get("/api/v1/thing")
    def thing() -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as client:
        alice = {"Authorization": f"Bearer {_token('alice')}"}
        bob = {"Authorization": f"Bearer {_token('bob')}"}

        assert client.get("/api/v1/thing", headers=alice).status_code == 200
        assert client.get("/api/v1/thing", headers=alice).status_code == 200
        assert client.get("/api/v1/thing", headers=alice).status_code == 429
        # Bob has his own budget.
        assert client.get("/api/v1/thing", headers=bob).status_code == 200


def test_a_malformed_token_falls_back_to_the_address_rather_than_failing() -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit=1, window_seconds=60.0)

    @app.get("/api/v1/thing")
    def thing() -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as client:
        broken = {"Authorization": "Bearer not-a-jwt"}
        assert client.get("/api/v1/thing", headers=broken).status_code == 200
        assert client.get("/api/v1/thing", headers=broken).status_code == 429


def test_the_window_reopens_after_it_expires() -> None:
    """A limit that never resets would lock a user out permanently."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit=1, window_seconds=0.05)

    @app.get("/api/v1/thing")
    def thing() -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as client:
        assert client.get("/api/v1/thing").status_code == 200
        assert client.get("/api/v1/thing").status_code == 429
        import time

        time.sleep(0.08)
        assert client.get("/api/v1/thing").status_code == 200
