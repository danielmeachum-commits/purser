"""Login / logout / service-token management."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from agent.db import session_scope
from api.auth import (
    Principal,
    get_principal,
    mint_service_token,
    mint_session_jwt,
    require_admin,
    verify_admin_password,
)
from api.config import Settings, get_settings
from api.models import AuthToken
from api.schemas import (
    LoginRequest,
    TokenCreated,
    TokenCreateRequest,
    TokenInfo,
    WhoAmI,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=204)
def login(
    body: LoginRequest, settings: Settings = Depends(get_settings)
) -> Response:
    if not verify_admin_password(body.password, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid password"
        )
    token = mint_session_jwt(settings)
    response = Response(status_code=204)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.jwt_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", status_code=204)
def logout(settings: Settings = Depends(get_settings)) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(settings.cookie_name, path="/")
    return response


@router.get("/me", response_model=WhoAmI)
def me(principal: Principal | None = Depends(get_principal)) -> WhoAmI:
    if principal is None:
        return WhoAmI(authenticated=False)
    return WhoAmI(authenticated=True, scope=principal.scope, source=principal.source)


@router.get("/tokens", response_model=list[TokenInfo])
def list_tokens(_: Principal = Depends(require_admin)) -> list[TokenInfo]:
    with session_scope() as s:
        rows = s.query(AuthToken).order_by(AuthToken.id.desc()).all()
        return [TokenInfo.model_validate(r) for r in rows]


@router.post("/tokens", response_model=TokenCreated, status_code=201)
def create_token(
    body: TokenCreateRequest, _: Principal = Depends(require_admin)
) -> TokenCreated:
    raw, digest = mint_service_token()
    with session_scope() as s:
        if s.query(AuthToken).filter_by(name=body.name).first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"token name {body.name!r} already exists",
            )
        row = AuthToken(name=body.name, token_hash=digest, scope=body.scope)
        s.add(row)
        s.flush()
        info = TokenInfo.model_validate(row)
    return TokenCreated(**info.model_dump(), token=raw)


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(
    token_id: int, _: Principal = Depends(require_admin)
) -> Response:
    with session_scope() as s:
        row = s.get(AuthToken, token_id)
        if row is None:
            raise HTTPException(status_code=404, detail="token not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.utcnow()
    return Response(status_code=204)
