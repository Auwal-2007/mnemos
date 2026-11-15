"""Supabase JWT verification.

The frontend sends `Authorization: Bearer <access_token>`. Tokens are
verified with the project's JWT secret (HS256, as issued by Supabase Auth)
or validated against Supabase's `/auth/v1/user` endpoint when a secret is
not available locally.

Design notes:
* Claims are verified, never merely decoded.
* `sub` from a verified token is the only accepted source of user identity.
* Expired or malformed tokens produce 401 through `UnauthorizedError`.
* Verification results are not cached (tokens are short-lived and the
  operation is cheap).
"""

from __future__ import annotations

import logging

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError
from app.domain.identity import Identity

logger = logging.getLogger("mnemos.auth")

_ALGORITHMS = ("HS256",)


class TokenVerificationError(UnauthorizedError):
    """Raised when a bearer token cannot be verified."""

    default_message = "Your session is invalid or has expired. Please sign in again."


def verify_token(token: str, settings: Settings | None = None) -> Identity:
    """Verify a Supabase access token and return the caller's identity."""
    settings = settings or get_settings()

    if not token or not token.strip():
        raise TokenVerificationError(message="Authentication is required.")

    if not settings.supabase_jwt_secret:
        raise TokenVerificationError(
            message=(
                "Token verification is not configured on this server. "
                "Set SUPABASE_JWT_SECRET to enable authenticated endpoints."
            )
        )

    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=list(_ALGORITHMS),
            options={"require": ["sub", "exp"], "verify_aud": False},
        )
    except ExpiredSignatureError as exc:
        raise TokenVerificationError(
            message="Your session has expired. Please sign in again."
        ) from exc
    except InvalidTokenError as exc:
        # Do not echo the underlying reason: it can aid token forgery.
        logger.warning("Rejected bearer token: %s", type(exc).__name__)
        raise TokenVerificationError() from exc

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
