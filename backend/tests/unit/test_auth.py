"""Tests for Supabase JWT verification.

These exercise the real verification path with locally signed tokens; no
network call to Supabase is involved.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from app.core.config import Settings
from app.core.errors import ConfigurationError, UnauthorizedError
from app.infrastructure.auth import (
    TokenVerificationError,
    reset_verification_cache,
    verify_token,
)

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


def test_no_verification_method_configured_is_a_server_error_not_a_credential_error() -> None:
    """With neither a secret nor a project configured, the fault is the server's.

    Returning 401 here told users to sign in again, which could never help
    because the server had no way to check any token. 503 with an actionable
    message sends them to the right place: the deployment's configuration.
    """
    with pytest.raises(ConfigurationError) as excinfo:
        verify_token(make_token(), Settings(_env_file=None, supabase_jwt_secret=""))
    assert excinfo.value.status_code == 503
    assert "SUPABASE_URL" in excinfo.value.message


def test_blank_token_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_token("   ", settings())


def test_error_is_unauthorized_status() -> None:
    with pytest.raises(UnauthorizedError) as excinfo:
        verify_token("not-a-token", settings())
    assert excinfo.value.status_code == 401


def test_identity_is_immutable() -> None:
    """Identity is a frozen dataclass: it cannot be mutated after verification."""
    identity = verify_token(make_token(), settings())
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.user_id = "someone-else"  # type: ignore[misc]


def test_identity_carries_no_token_material() -> None:
    """The Identity object must not retain the raw JWT."""
    token = make_token()
    identity = verify_token(token, settings())
    assert token not in repr(identity)


# ---------------------------------------------------------------------------
# Remote verification (asymmetric-key projects)
#
# Supabase projects created recently sign tokens with ES256/RS256 and the
# project's JWT secret does not sign them at all. A local HS256 check therefore
# fails on every request no matter how the secret is configured, which is what
# produced the "you must sign in" loop. These tests cover the second strategy.
# ---------------------------------------------------------------------------

ANOON = "anon-key-for-tests"


def remote_settings(**overrides: object) -> Settings:
    base = {
        "supabase_url": "https://abcdefghijklm.supabase.co",
        "supabase_anon_key": ANOON,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


class _Response:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


def test_remote_verification_is_used_when_no_secret_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The token need not be HS256; the issuer confirms it."""
    reset_verification_cache()
    seen: dict[str, object] = {}

    def fake_get(url: str, headers: dict[str, str], timeout: float) -> _Response:
        seen["url"] = url
        seen["headers"] = headers
        return _Response(
            200, {"id": USER_ID, "email": "alice@mnemos.test", "role": "authenticated"}
        )

    monkeypatch.setattr("app.infrastructure.auth.httpx.get", fake_get)

    identity = verify_token("opaque-asymmetric-token", remote_settings())

    assert identity.user_id == USER_ID
    assert identity.email == "alice@mnemos.test"
    assert seen["url"] == "https://abcdefghijklm.supabase.co/auth/v1/user"
    assert seen["headers"] == {
        "Authorization": "Bearer opaque-asymmetric-token",
        "apikey": ANOON,
    }


def test_remote_verification_is_used_when_a_local_signature_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrong-secret signature is expected on asymmetric projects.

    The local failure says nothing about the token's validity, so the issuer is
    asked rather than the user rejected.
    """
    reset_verification_cache()
    monkeypatch.setattr(
        "app.infrastructure.auth.httpx.get",
        lambda url, headers, timeout: _Response(200, {"id": USER_ID, "email": None}),
    )
    token = make_token(secret="a-different-secret-entirely-32-chars")
    identity = verify_token(token, remote_settings(supabase_jwt_secret=SECRET))
    assert identity.user_id == USER_ID
    assert identity.email is None


def test_an_expired_token_is_rejected_without_a_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expiry is knowable locally; spending a request on it would be waste."""
    reset_verification_cache()
    called = {"value": False}

    def fail_get(*args: object, **kwargs: object) -> _Response:
        called["value"] = True
        raise AssertionError("network must not be used for an expired token")

    monkeypatch.setattr("app.infrastructure.auth.httpx.get", fail_get)

    with pytest.raises(TokenVerificationError, match="expired"):
        verify_token(
            make_token(exp_delta=-60),
            remote_settings(supabase_jwt_secret=SECRET),
        )
    assert called["value"] is False


def test_a_token_the_issuer_rejects_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_verification_cache()
    monkeypatch.setattr(
        "app.infrastructure.auth.httpx.get",
        lambda url, headers, timeout: _Response(401),
    )
    with pytest.raises(TokenVerificationError):
        verify_token("bad-token", remote_settings())


def test_an_unreachable_auth_service_is_a_server_error_not_a_bad_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user's session is fine; the server could not check it.

    Reporting 401 here would tell them to sign in again, which cannot help and
    would loop them through re-authentication against a working session.
    """
    reset_verification_cache()

    def raise_transport(*args: object, **kwargs: object) -> _Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr("app.infrastructure.auth.httpx.get", raise_transport)

    with pytest.raises(ConfigurationError) as excinfo:
        verify_token("any-token", remote_settings())
    assert excinfo.value.status_code == 503
    assert "not a problem with your credentials" in excinfo.value.message


def test_successful_remote_verification_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A page load makes many calls; one verification should serve them all."""
    reset_verification_cache()
    calls = {"count": 0}

    def counting_get(url: str, headers: dict[str, str], timeout: float) -> _Response:
        calls["count"] += 1
        return _Response(200, {"id": USER_ID, "email": None})

    monkeypatch.setattr("app.infrastructure.auth.httpx.get", counting_get)
    settings_obj = remote_settings()

    verify_token("cache-me", settings_obj)
    verify_token("cache-me", settings_obj)
    verify_token("cache-me", settings_obj)

    assert calls["count"] == 1


def test_rejections_are_never_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caching a rejection would turn a transient blip into a lockout."""
    reset_verification_cache()
    calls = {"count": 0}

    def rejecting_get(url: str, headers: dict[str, str], timeout: float) -> _Response:
        calls["count"] += 1
        return _Response(401)

    monkeypatch.setattr("app.infrastructure.auth.httpx.get", rejecting_get)
    settings_obj = remote_settings()

    for _ in range(2):
        with pytest.raises(TokenVerificationError):
            verify_token("rejected", settings_obj)

    assert calls["count"] == 2


def test_changing_the_configuration_invalidates_a_cached_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotating a key must not keep accepting previously verified tokens.

    Proven by call count rather than by failure: after a configuration change the
    token must be re-checked with the issuer, because the previous verification
    says nothing about the new project.
    """
    reset_verification_cache()
    calls = {"count": 0}

    def counting_get(url: str, headers: dict[str, str], timeout: float) -> _Response:
        calls["count"] += 1
        return _Response(200, {"id": USER_ID, "email": None})

    monkeypatch.setattr("app.infrastructure.auth.httpx.get", counting_get)

    verify_token("token", remote_settings())
    verify_token("token", remote_settings())
    assert calls["count"] == 1, "same configuration should reuse the cached identity"

    verify_token("token", remote_settings(supabase_url="https://otherproject.supabase.co"))
    assert calls["count"] == 2, "a different project must trigger a fresh verification"


def test_cache_does_not_store_the_raw_token(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_verification_cache()
    monkeypatch.setattr(
        "app.infrastructure.auth.httpx.get",
        lambda url, headers, timeout: _Response(200, {"id": USER_ID, "email": None}),
    )
    verify_token("supersecret-token-value", remote_settings())

    from app.infrastructure import auth as auth_module

    keys = list(auth_module._cache.keys())
    assert keys, "expected a cached entry"
    assert all("supersecret-token-value" not in key for key in keys)
