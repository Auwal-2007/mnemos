"""Tests for Supabase JWT verification.

These exercise the real verification path with locally signed tokens; no
network call to Supabase is involved.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.infrastructure.auth import TokenVerificationError, verify_token

SECRET = "test-jwt-secret-with-at-least-32-characters-long"
USER_ID = "11111111-1111-4111-8111-111111111111"


def settings(**overrides: object) -> Settings:
    base = {"supabase_url": "https://abcdefghijklm.supabase.co", "supabase_jwt_secret": SECRET}
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def make_token(
    *,
    sub: str | None = USER_ID,
    exp_delta: int = 3600,
    secret: str = SECRET,
    algorithm: str = "HS256",
    **claims: object,
) -> str:
    payload: dict[str, object] = {
        "exp": datetime.now(UTC) + timedelta(seconds=exp_delta),
        "email": "alice@mnemos.test",
        "role": "authenticated",
        **claims,
    }
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_valid_token_returns_identity() -> None:
    identity = verify_token(make_token(), settings())
    assert identity.user_id == USER_ID
    assert identity.email == "alice@mnemos.test"
    assert identity.role == "authenticated"
    assert identity.is_service is False


def test_service_role_token_is_flagged() -> None:
    identity = verify_token(make_token(role="service_role"), settings())
    assert identity.is_service is True


def test_expired_token_is_rejected() -> None:
    with pytest.raises(TokenVerificationError) as excinfo:
        verify_token(make_token(exp_delta=-60), settings())
    assert "expired" in excinfo.value.message.lower()


def test_wrong_secret_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_token(make_token(secret="a-different-secret-value-32-chars-min"), settings())


def test_token_without_subject_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_token(make_token(sub=None), settings())


def test_token_without_expiry_is_rejected() -> None:
    unsigned = jwt.encode({"sub": USER_ID}, SECRET, algorithm="HS256")
    # PyJWT adds no exp; our decode requires it.
    with pytest.raises(TokenVerificationError):
        verify_token(unsigned, settings())


def test_alg_none_is_rejected() -> None:
    """An unsigned token must never be accepted."""
    forged = jwt.encode({"sub": USER_ID, "exp": time.time() + 600}, None, algorithm="none")
    with pytest.raises(TokenVerificationError):
        verify_token(forged, settings())


def test_missing_secret_raises_configuration_error() -> None:
    with pytest.raises(TokenVerificationError):
        verify_token(make_token(), Settings(_env_file=None, supabase_jwt_secret=""))


def test_blank_token_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_token("   ", settings())


def test_error_is_unauthorized_status() -> None:
    with pytest.raises(UnauthorizedError) as excinfo:
        verify_token("not-a-token", settings())
    assert excinfo.value.status_code == 401


def test_identity_is_immutable() -> None:
    identity = verify_token(make_token(), settings())
    with pytest.raises(Exception):
        identity.user_id = "someone-else"  # type: ignore[misc]


def test_identity_carries_no_token_material() -> None:
    """The Identity object must not retain the raw JWT."""
    token = make_token()
    identity = verify_token(token, settings())
    assert token not in repr(identity)
