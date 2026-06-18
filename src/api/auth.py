"""Authentication primitives: passwords, JWT sessions, service tokens.

Two credentials grant access:

- A short-lived JWT in an httpOnly cookie, minted on `POST /auth/login`
  with the admin password. Carries the `admin` scope.
- A long-lived service token (`bgt_<random>`) sent as `Authorization:
  Bearer <token>` or `?token=<token>` (for WebSockets). Each row in
  `auth_tokens` records the scope ("admin" or "read").

Service tokens are stored as sha256(plaintext) — the raw value is shown
once at creation and discarded. Admin password is bcrypt-verified.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, status
from passlib.context import CryptContext

from agent.db import session_scope
from api.config import Settings, get_settings
from api.models import AuthToken

Scope = Literal["admin", "read"]
SERVICE_TOKEN_PREFIX = "bgt_"

# `passlib` warns at import without a configured handler.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass(frozen=True)
class Principal:
    """The authenticated caller for a request."""

    scope: Scope
    source: Literal["session", "token"]
    token_id: int | None = None  # set when source=='token'


# --- passwords -------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash for the given plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verification."""
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def verify_admin_password(plain: str, settings: Settings) -> bool:
    """Check the supplied password against the configured admin secret.

    The configured value can be either a bcrypt hash (starts with `$2`)
    or a plaintext string — plaintext is compared with a constant-time
    equality check.
    """
    configured = settings.admin_password
    if configured.startswith("$2"):
        return verify_password(plain, configured)
    return hmac.compare_digest(plain.encode(), configured.encode())


# --- JWT sessions ----------------------------------------------------------


def mint_session_jwt(settings: Settings) -> str:
    """Mint a short-lived admin session JWT."""
    now = int(time.time())
    payload = {
        "sub": "admin",
        "scope": "admin",
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_session_jwt(token: str, settings: Settings) -> dict | None:
    """Return the decoded payload, or None if invalid/expired."""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None


# --- service tokens --------------------------------------------------------


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def mint_service_token() -> tuple[str, str]:
    """Generate a fresh service token. Returns (plaintext, sha256_hex)."""
    raw = SERVICE_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


def resolve_service_token(raw: str) -> Principal | None:
    """Look up an active service token, return its Principal, or None."""
    if not raw or not raw.startswith(SERVICE_TOKEN_PREFIX):
        return None
    digest = _hash_token(raw)
    with session_scope() as s:
        row = s.query(AuthToken).filter_by(token_hash=digest).first()
        if row is None or row.revoked_at is not None:
            return None
        # Update last_used_at — best-effort.
        from datetime import datetime as _dt

        row.last_used_at = _dt.utcnow()
        scope: Scope = "admin" if row.scope == "admin" else "read"
        return Principal(scope=scope, source="token", token_id=row.id)


# --- FastAPI dependencies --------------------------------------------------


def _principal_from_cookie(
    cookie_value: str | None, settings: Settings
) -> Principal | None:
    if not cookie_value:
        return None
    payload = decode_session_jwt(cookie_value, settings)
    if not payload or payload.get("scope") != "admin":
        return None
    return Principal(scope="admin", source="session")


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def get_principal(
    request: Request,
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
    session: str | None = Cookie(default=None, alias="budget_session"),
    token: str | None = Query(default=None),
) -> Principal | None:
    """Resolve the caller — cookie, Bearer header, or ?token=... query."""
    # FastAPI's Cookie() alias is fixed at decl-time; pull the real cookie name.
    cookie_value = request.cookies.get(settings.cookie_name) or session
    p = _principal_from_cookie(cookie_value, settings)
    if p:
        return p
    raw = _bearer_token(authorization) or token
    if raw:
        return resolve_service_token(raw)
    return None


def require_reader(
    principal: Principal | None = Depends(get_principal),
) -> Principal:
    """Allow admin sessions and any active service token (read or admin)."""
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return principal


def require_admin(
    principal: Principal | None = Depends(get_principal),
) -> Principal:
    """Allow admin sessions and admin-scoped service tokens only."""
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    if principal.scope != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin scope required"
        )
    return principal
