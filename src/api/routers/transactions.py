"""Transactions list, create, update, delete."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from agent import queries
from agent.db import (
    Account,
    Category,
    Transaction,
    TransactionType,
    session_scope,
)
from agent.queries import _serialize_tx
from api import poller
from api.auth import Principal, require_admin, require_reader
from api.pubsub import broadcast
from api.schemas import TransactionUpdate

router = APIRouter(tags=["transactions"])


class TransactionCreate(BaseModel):
    """POST /transactions body — no interrupt; the admin form is the confirm."""

    amount: float | str
    type: Literal["income", "expense", "transfer"]
    description: str = Field(min_length=1, max_length=255)
    date: date_type | None = None
    category: str | None = None
    account: str | None = None
    is_test: bool = False


def _parse_amount(amount: float | int | str) -> Decimal:
    try:
        d = Decimal(str(amount))
    except InvalidOperation as e:
        raise HTTPException(status_code=400, detail=f"invalid amount: {amount!r}") from e
    if d <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    return d


@router.get("/transactions")
def list_transactions(
    limit: int = Query(default=50, ge=1, le=500),
    date_range: str | None = Query(default=None),
    since_date: str | None = Query(default=None),
    until_date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account: str | None = Query(default=None),
    type: str | None = Query(default=None),
    test_mode: str = Query(default="exclude"),
    _: Principal = Depends(require_reader),
) -> list[dict]:
    result = queries.list_transactions(
        limit=limit,
        date_range=date_range,
        since_date=since_date,
        until_date=until_date,
        category=category,
        account=account,
        type=type,
        test_mode=test_mode,
    )
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/transactions/{tx_id}")
def get_transaction(
    tx_id: int, _: Principal = Depends(require_reader)
) -> dict:
    tx = queries.get_transaction(tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return tx


def _resolve_category(s, name: str, tt: TransactionType) -> Category:
    matches = s.query(Category).filter_by(name=name, type_id=tt.id).all()
    if not matches:
        raise HTTPException(
            status_code=400,
            detail=f"no {tt.name} category named {name!r}",
        )
    if len(matches) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"category {name!r} is ambiguous ({len(matches)} matches)",
        )
    return matches[0]


def _resolve_account(s, name: str) -> Account:
    acct = s.query(Account).filter_by(nickname=name).first()
    if acct is None:
        raise HTTPException(
            status_code=400, detail=f"no account with nickname {name!r}"
        )
    return acct


@router.post("/transactions", status_code=201)
def create_transaction(
    body: TransactionCreate, _: Principal = Depends(require_admin)
) -> dict:
    amount = _parse_amount(body.amount)
    tx_date = body.date or date_type.today()
    with session_scope() as s:
        tt = s.query(TransactionType).filter_by(name=body.type).first()
        if tt is None:
            raise HTTPException(
                status_code=400, detail=f"unknown transaction type {body.type!r}"
            )
        cat = _resolve_category(s, body.category, tt) if body.category else None
        acct = _resolve_account(s, body.account) if body.account else None
        tx = Transaction(
            date=tx_date,
            amount=amount,
            type=tt,
            category=cat,
            account=acct,
            description=body.description,
            is_test=body.is_test,
        )
        s.add(tx)
        s.flush()
        result = _serialize_tx(tx)
        created_at = tx.created_at
    broadcast({"type": "transaction.new", "transaction": result})
    poller.mark_broadcast(created_at)
    return result


@router.patch("/transactions/{tx_id}")
def update_transaction(
    tx_id: int, body: TransactionUpdate, _: Principal = Depends(require_admin)
) -> dict:
    with session_scope() as s:
        tx = s.get(Transaction, tx_id)
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        if body.type is not None:
            tt = s.query(TransactionType).filter_by(name=body.type).first()
            if tt is None:
                raise HTTPException(
                    status_code=400, detail=f"unknown type {body.type!r}"
                )
            tx.type = tt
        if body.date is not None:
            tx.date = body.date
        if body.amount is not None:
            tx.amount = _parse_amount(body.amount)
        if body.description is not None:
            tx.description = body.description
        if body.is_test is not None:
            tx.is_test = body.is_test
        if body.category is not None:
            if body.category == "":
                tx.category = None
            else:
                tx.category = _resolve_category(s, body.category, tx.type)
        if body.account is not None:
            tx.account = None if body.account == "" else _resolve_account(s, body.account)
        s.flush()
        result = _serialize_tx(tx)
    broadcast({"type": "transaction.updated", "transaction": result})
    return result


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(
    tx_id: int, _: Principal = Depends(require_admin)
) -> Response:
    with session_scope() as s:
        tx = s.get(Transaction, tx_id)
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        s.delete(tx)
    broadcast({"type": "transaction.deleted", "id": tx_id})
    return Response(status_code=204)
