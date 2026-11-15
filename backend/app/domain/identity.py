"""Authenticated identity.

`Identity` is only ever constructed from a verified Supabase JWT. Client
supplied user ids are never trusted as proof of identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified authenticated user."""

    user_id: str
    email: str | None
    role: str
    expires_at: datetime | None = None

    @property
    def is_service(self) -> bool:
        """True for service-role tokens (server-to-server only)."""
        return self.role == "service_role"
