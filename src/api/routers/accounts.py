"""Accounts and account types — read + admin writes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from agent import queries
from agent.db import Account, AccountType, Transaction, session_scope
from api.auth import Principal, require_admin, require_reader
from api.pubsub import broadcast
from api.schemas import AccountCreate, AccountTypeCreate, AccountUpdate

router = APIRouter(tags=["accounts"])


# --- reads -----------------------------------------------------------------


@router.get("/accounts")
def list_accounts(
    include_inactive: bool = Query(default=False),
    _: Principal = Depends(require_reader),
) -> list[dict]:
    return queries.list_accounts(include_inactive=include_inactive)


@router.get("/account-types")
def list_account_types(_: Principal = Depends(require_reader)) -> list[dict]:
    return queries.list_account_types()


@router.get("/transaction-types")
def list_transaction_types(_: Principal = Depends(require_reader)) -> list[dict]:
    return queries.list_transaction_types()


# --- account writes --------------------------------------------------------


def _serialize(a: Account) -> dict:
    return {
        "id": a.id,
        "nickname": a.nickname,
        "bank_name": a.bank_name,
        "account_type": a.account_type.name,
        "last_four": a.last_four,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _validate_last_four(value: str | None) -> None:
    if value is not None and (not value.isdigit() or len(value) > 4):
        raise HTTPException(
            status_code=400, detail=f"last_four must be up to 4 digits; got {value!r}"
        )


@router.post("/accounts", status_code=201)
def create_account(
    body: AccountCreate, _: Principal = Depends(require_admin)
) -> dict:
    _validate_last_four(body.last_four)
    with session_scope() as s:
        at = s.query(AccountType).filter_by(name=body.account_type).first()
        if at is None:
            raise HTTPException(
                status_code=400,
                detail=f"unknown account_type {body.account_type!r}",
            )
        if s.query(Account).filter_by(nickname=body.nickname).first() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"account nickname {body.nickname!r} already exists",
            )
        acct = Account(
            nickname=body.nickname,
            bank_name=body.bank_name,
            account_type=at,
            last_four=body.last_four,
        )
        s.add(acct)
        s.flush()
        result = _serialize(acct)
    broadcast({"type": "account.new", "account": result})
    return result


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: int, body: AccountUpdate, _: Principal = Depends(require_admin)
) -> dict:
    _validate_last_four(body.last_four)
    with session_scope() as s:
        acct = s.get(Account, account_id)
        if acct is None:
            raise HTTPException(status_code=404, detail="account not found")
        if body.nickname is not None and body.nickname != acct.nickname:
            if s.query(Account).filter_by(nickname=body.nickname).first() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"account nickname {body.nickname!r} already exists",
                )
            acct.nickname = body.nickname
        if body.bank_name is not None:
            acct.bank_name = body.bank_name
        if body.account_type is not None:
            at = s.query(AccountType).filter_by(name=body.account_type).first()
            if at is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown account_type {body.account_type!r}",
                )
            acct.account_type = at
        if body.last_four is not None:
            acct.last_four = body.last_four
        if body.is_active is not None:
            acct.is_active = body.is_active
        s.flush()
        result = _serialize(acct)
    broadcast({"type": "account.updated", "account": result})
    return result


# --- account_type writes ---------------------------------------------------


@router.post("/account-types", status_code=201)
def create_account_type(
    body: AccountTypeCreate, _: Principal = Depends(require_admin)
) -> dict:
    with session_scope() as s:
        if s.query(AccountType).filter_by(name=body.name).first() is not None:
            raise HTTPException(
                status_code=409, detail=f"account_type {body.name!r} already exists"
            )
        row = AccountType(name=body.name)
        s.add(row)
        s.flush()
        result = {"id": row.id, "name": row.name}
    broadcast({"type": "account_type.new", "account_type": result})
    return result


@router.delete("/account-types/{type_id}", status_code=204)
def delete_account_type(
    type_id: int, _: Principal = Depends(require_admin)
) -> Response:
    with session_scope() as s:
        row = s.get(AccountType, type_id)
        if row is None:
            raise HTTPException(status_code=404, detail="account_type not found")
        in_use = s.query(Account).filter_by(account_type_id=type_id).first()
        if in_use is not None:
            raise HTTPException(
                status_code=409,
                detail="account_type is in use by at least one account",
            )
        s.delete(row)
    broadcast({"type": "account_type.deleted", "id": type_id})
    return Response(status_code=204)


# Keep an explicit reference so unused-import linters don't complain.
_ = Transaction
