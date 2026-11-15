"""Integration tests for application startup and imports."""

from app.main import app


def test_app_imports_and_has_routes() -> None:
    """Application imports cleanly and exposes health routes."""
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/" in paths


def test_app_title() -> None:
    """Application metadata is set."""
    assert app.title == "MNEMOS API"
