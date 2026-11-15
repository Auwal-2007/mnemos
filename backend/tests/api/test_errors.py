"""Tests for error handling and validation behaviour."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import NotFoundError, UnauthorizedError
from app.main import create_app


class _Payload(BaseModel):
    title: str
    count: int


def _client_with_probe_routes() -> TestClient:
    """Build a test app exposing probe routes that raise domain errors."""
    application: FastAPI = create_app()

    @application.get("/probe/not-found")
    async def _not_found() -> None:
        raise NotFoundError("Knowledge entry not found.")

    @application.get("/probe/unauthorized")
    async def _unauthorized() -> None:
        raise UnauthorizedError()

    @application.post("/probe/validate")
    async def _validate(payload: _Payload) -> _Payload:
        return payload

    return TestClient(application, raise_server_exceptions=False)


def test_domain_error_uses_envelope() -> None:
    """Domain errors map to their status code and canonical envelope."""
    response = _client_with_probe_routes().get("/probe/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Knowledge entry not found."


def test_unauthorized_uses_default_message() -> None:
    """Errors without an explicit message use their default."""
    response = _client_with_probe_routes().get("/probe/unauthorized")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_request_validation_reports_field_paths() -> None:
    """Pydantic validation failures return 422 with field-level details."""
    response = _client_with_probe_routes().post("/probe/validate", json={"title": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    paths = {detail["path"] for detail in body["error"]["details"]}
    assert any(path.endswith("count") for path in paths)


def test_valid_payload_round_trips() -> None:
    """Valid request bodies are accepted and returned by the schema."""
    response = _client_with_probe_routes().post("/probe/validate", json={"title": "x", "count": 2})
    assert response.status_code == 200
    assert response.json() == {"title": "x", "count": 2}
