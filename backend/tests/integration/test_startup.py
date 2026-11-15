"""Integration tests for application startup, routing and lifecycle."""

from fastapi.testclient import TestClient

from app.main import app, create_app
from app.services.health_service import APP_VERSION


def test_app_exposes_health_routes() -> None:
    """Application exposes health routes under both prefixes."""
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/ready" in paths


def test_app_metadata() -> None:
    """Application metadata is set for OpenAPI documentation."""
    assert app.title == "MNEMOS API"
    assert app.version == APP_VERSION


def test_lifespan_runs_cleanly() -> None:
    """Application starts and shuts down via the lifespan context."""
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


def test_cors_allows_configured_origin() -> None:
    """CORS preflight succeeds for the configured development origin."""
    client = TestClient(create_app())
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_exposes_request_id_header() -> None:
    """Actual CORS responses expose the correlation header to browsers."""
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "x-request-id" in exposed.lower()
