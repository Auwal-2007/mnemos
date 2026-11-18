"""Supabase JWT verification.

The frontend sends ``Authorization: Bearer <access_token>``. Verification has
two strategies, and which one is correct depends on how the Supabase project
signs its tokens — not on a preference.

Why two strategies
------------------
Supabase projects created recently sign access tokens with **asymmetric** keys
(ES256/RS256) by default. The project's "JWT secret" no longer signs those
tokens, so verifying them with HS256 fails no matter how the secret is copied.
Older projects still use a shared HS256 secret.

A deployment that only implements HS256 therefore works on legacy projects and
fails on every new one, with the misleading message "your session is invalid".
That is exactly the failure this module now avoids:

1. **Local HS256** when ``SUPABASE_JWT_SECRET`` is configured. Fast, no network,
   and correct for legacy projects.
2. **Supabase Auth** (``GET {url}/auth/v1/user``) otherwise, or when the local
   signature does not match. This asks the issuer to confirm its own token, so it
   is correct for *any* signing algorithm, including asymmetric keys, and needs
   no secret at all — only the project URL and the public anon key.

The second strategy costs a network round trip, so successful results are cached
briefly. Rejections are never cached.

Design notes
* Claims are verified, never merely decoded.
* ``sub`` from a verified token is the only accepted source of user identity.
* An expired token is rejected without a network call: expiry is checkable
  locally and asking the issuer about a token we already know is dead wastes a
  request per retry loop.
* A failure to *reach* the auth service is reported as a configuration/service
  error (503), not as a bad credential (401). Telling a user their session is
  invalid when the server simply could not check it is a lie, and it sends them
  to re-authenticate against a working session.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass

import httpx
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, UnauthorizedError
from app.domain.identity import Identity

logger = logging.getLogger("mnemos.auth")

_ALGORITHMS = ("HS256",)

#: How long a successful remote verification is trusted, in seconds.
#:
#: A short window is a deliberate trade: it removes one network round trip per
#: API call, at the cost of a revoked token staying usable for up to this long.
#: One minute keeps that exposure small while still collapsing the burst of
#: calls a page load produces.
VERIFICATION_CACHE_TTL_SECONDS = 60.0

#: Ceiling on cached identities, so the cache cannot grow without bound.
_CACHE_LIMIT = 4096

_TIMEOUT_SECONDS = 5.0


class TokenVerificationError(UnauthorizedError):
    """Raised when a bearer token cannot be verified."""

    default_message = "Your session is invalid or has expired. Please sign in again."


@dataclass(slots=True)
class _CacheEntry:
    identity: Identity
    expires_at: float


_cache: dict[str, _CacheEntry] = {}
_cache_lock = threading.Lock()


def reset_verification_cache() -> None:
    """Clear the verification cache. Used by tests and after a key rotation."""
    with _cache_lock:
        _cache.clear()


def _cache_key(token: str, settings: Settings) -> str:
    """Key on the token *and* the verification configuration.

    Including the configuration is not incidental. Keyed on the token alone, an
    identity verified under one set of credentials would keep being accepted
    after the project URL, anon key or signing secret changed — so rotating a
    secret would silently fail to invalidate anything already cached. Hashing
    the whole input also means the cache never holds a usable credential.
    """
    material = "\x00".join(
        (
            token,
            settings.supabase_url,
            settings.supabase_anon_key,
            settings.supabase_jwt_secret,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _cache_get(token: str, settings: Settings) -> Identity | None:
    key = _cache_key(token, settings)
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            _cache.pop(key, None)
            return None
        return entry.identity


def _cache_put(token: str, identity: Identity, settings: Settings) -> None:
    with _cache_lock:
        if len(_cache) >= _CACHE_LIMIT:
            now = time.monotonic()
            for stale in [k for k, v in _cache.items() if now >= v.expires_at]:
                _cache.pop(stale, None)
            if len(_cache) >= _CACHE_LIMIT:
                _cache.clear()
        _cache[_cache_key(token, settings)] = _CacheEntry(
            identity=identity,
            expires_at=time.monotonic() + VERIFICATION_CACHE_TTL_SECONDS,
        )


def verify_token(token: str, settings: Settings | None = None) -> Identity:
    """Verify a Supabase access token and return the caller's identity.

    Raises :class:`TokenVerificationError` (401) when the token is not valid, and
    :class:`ConfigurationError` (503) when no verification method is available or
    the auth service cannot be reached.
    """
    settings = settings or get_settings()

    if not token or not token.strip():
        raise TokenVerificationError(message="Authentication is required.")

    cached = _cache_get(token, settings)
    if cached is not None:
        return cached

    identity = _verify(token, settings)
    _cache_put(token, identity, settings)
    return identity


def _verify(token: str, settings: Settings) -> Identity:
    """Apply the available strategies in order of cost."""
    secret = settings.supabase_jwt_secret
    url = settings.supabase_url
    anon_key = settings.supabase_anon_key
    has_remote = bool(url and anon_key)

    if not secret and not has_remote:
        raise ConfigurationError(
            message=(
                "Token verification is not configured on this server. Set "
                "SUPABASE_URL and SUPABASE_ANON_KEY (recommended: works with any "
                "signing algorithm), or SUPABASE_JWT_SECRET for a legacy HS256 "
                "project."
            )
        )

    local_failure: TokenVerificationError | None = None
    if secret:
        try:
            return _verify_local(token, secret)
        except TokenVerificationError as exc:
            # Expiry is knowable locally; asking the issuer about a token we can
            # already prove is dead only adds a request to every retry loop.
            if getattr(exc, "is_expired", False):
                raise
            local_failure = exc
            if not has_remote:
                raise

    # Reached only when remote verification is configured. A signature that
    # fails locally is expected on asymmetric-key projects and says nothing
    # about the token, so the issuer is asked rather than the user rejected.
    if local_failure is not None:
        logger.debug("Local HS256 verification failed; deferring to Supabase Auth")
    return _verify_remote(token, url, anon_key)


class _ExpiredToken(TokenVerificationError):
    """A token whose expiry has passed. Flagged so callers skip the network."""

    is_expired = True


def _verify_local(token: str, secret: str) -> Identity:
    """Verify an HS256 token against the project's shared secret."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=list(_ALGORITHMS),
            options={"require": ["sub", "exp"], "verify_aud": False},
        )
    except ExpiredSignatureError as exc:
        raise _ExpiredToken(message="Your session has expired. Please sign in again.") from exc
    except InvalidTokenError as exc:
        # Do not echo the underlying reason: it can aid token forgery.
        logger.warning("Rejected bearer token: %s", type(exc).__name__)
        raise TokenVerificationError() from exc

    return _identity_from_claims(claims)


def _identity_from_claims(claims: dict[str, object]) -> Identity:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenVerificationError()

    email = claims.get("email")
    role = claims.get("role", "authenticated")

    return Identity(
        user_id=subject,
        email=email if isinstance(email, str) else None,
        role=role if isinstance(role, str) else "authenticated",
    )


def _verify_remote(token: str, supabase_url: str, anon_key: str) -> Identity:
    """Ask Supabase Auth to confirm the token.

    This is algorithm-agnostic: the issuer validates its own signature, so it
    works for HS256, ES256 and RS256 projects alike. It requires only the public
    anon key, not the signing secret.
    """
    url = f"{supabase_url.rstrip('/')}/auth/v1/user"
    headers = {"Authorization": f"Bearer {token}", "apikey": anon_key}

    try:
        response = httpx.get(url, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ConfigurationError(
            message=(
                "The authentication service could not be reached, so your session "
                "could not be confirmed. This is a server-side problem, not a "
                "problem with your credentials."
            )
        ) from exc

    if response.status_code in (401, 403):
        logger.warning("Supabase Auth rejected a bearer token (%s)", response.status_code)
        raise TokenVerificationError()

    if response.status_code >= 500:
        raise ConfigurationError(
            message=(
                "The authentication service is unavailable, so your session could "
                "not be confirmed. Please try again shortly."
            )
        )

    if response.status_code != 200:
        logger.warning("Unexpected Supabase Auth response (%s)", response.status_code)
        raise TokenVerificationError()

    try:
        user = response.json()
    except ValueError as exc:
        raise ConfigurationError(
            message="The authentication service returned an unreadable response."
        ) from exc

    if not isinstance(user, dict):
        raise TokenVerificationError()

    role = user.get("role")
    email = user.get("email")
    return _identity_from_claims(
        {
            "sub": user.get("id"),
            "email": email if isinstance(email, str) else None,
            "role": role if isinstance(role, str) else "authenticated",
        }
    )


__all__ = [
    "VERIFICATION_CACHE_TTL_SECONDS",
    "TokenVerificationError",
    "reset_verification_cache",
    "verify_token",
]
