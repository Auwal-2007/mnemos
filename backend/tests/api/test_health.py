"""API tests for the health-check endpoint (FR-015)."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """GET /health returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "mnemos"
    assert body["version"] == "0.0.1"


def test_root_returns_skeleton_status(client: TestClient) -> None:
    """GET / returns the Phase 0 skeleton status."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "phase-0-skeleton"
