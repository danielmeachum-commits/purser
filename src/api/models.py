"""SQLAlchemy models owned by the API (registered against agent.db.Base)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from agent.db import Base


class AuthToken(Base):
    """A long-lived service token for the API.

    `token_hash` is sha256 hex of the raw token bytes — the plaintext is
    shown to the operator once at creation and never stored.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"AuthToken(id={self.id}, name={self.name!r}, scope={self.scope!r}, "
            f"revoked={self.revoked_at is not None})"
        )
