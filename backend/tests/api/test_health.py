"""API tests for health and readiness endpoints (FR-015)."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """GET /health returns 200 with the liveness payload."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "mnemos"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "development"


def test_versioned_health_route(client: TestClient) -> None:
    """Health is available under the versioned API prefix."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_does_not_leak_configuration(client: TestClient) -> None:
    """Health responses expose no secrets or infrastructure values."""
    text = client.get("/health").text.lower()
    for forbidden in ("key", "secret", "password", "postgres", "supabase_url", "token"):
        assert forbidden not in text


def test_readiness_reports_presence_only(client: TestClient) -> None:
    """Readiness lists integrations without revealing their values."""
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    names = {check["name"] for check in body["checks"]}
    assert {"supabase", "supabase_auth", "openrouter"} <= names


def test_request_id_header_is_returned(client: TestClient) -> None:
    """Every response carries a correlation id."""
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_request_id_is_propagated_when_safe(client: TestClient) -> None:
    """A safe client-supplied correlation id is echoed back."""
    response = client.get("/health", headers={"X-Request-ID": "test-correlation-123"})
    assert response.headers["X-Request-ID"] == "test-correlation-123"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    """404s use the canonical error envelope with a request id."""
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"]
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


def test_openapi_schema_is_available(client: TestClient) -> None:
    """OpenAPI documentation is generated for the versioned API."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/health" in schema["paths"]
    assert schema["info"]["title"] == "MNEMOS API"
