"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """API runtime settings.

    Read once at startup. All fields override-able via env vars.
    """

    admin_password: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 60 * 60 * 12  # 12 h
    cookie_name: str = "budget_session"
    cookie_secure: bool = False  # local-only by default
    cors_origins: tuple[str, ...] = field(default_factory=lambda: ("http://localhost:5173",))
    poll_interval_seconds: float = 3.0


def _split_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(s.strip() for s in value.split(",") if s.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings(
        admin_password=os.environ.get("ADMIN_PASSWORD", "change-me"),
        jwt_secret=os.environ.get("JWT_SECRET", "dev-secret-change-me"),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_ttl_seconds=int(os.environ.get("JWT_TTL_SECONDS", str(60 * 60 * 12))),
        cookie_name=os.environ.get("COOKIE_NAME", "budget_session"),
        cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        cors_origins=_split_csv(
            os.environ.get("CORS_ORIGINS"),
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        ),
        poll_interval_seconds=float(os.environ.get("POLL_INTERVAL_SECONDS", "3.0")),
    )
