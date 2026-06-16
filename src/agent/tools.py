"""LangChain tools exposed to the agent for managing transactions."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import func as sa_func
from sqlalchemy.exc import NoResultFound

from agent.db import (
    Account,
    AccountType,
    Category,
    Transaction,
    TransactionType,
    session_scope,
)


def _parse_date(s: str | None) -> date_type:
    if s is None:
        return date_type.today()
    return date_type.fromisoformat(s)


def _parse_amount(amount: float | int | str) -> Decimal:
    try:
        return Decimal(str(amount))
    except InvalidOperation as e:
        raise ValueError(f"invalid amount: {amount!r}") from e


@tool
def record_transaction(
    amount: float,
    type: str,
    description: str,
    date: str | None = None,
    category: str | None = None,
    account: str | None = None,
    is_test: bool = False,
) -> str:
    """Record a single financial transaction.

    Args:
        amount: Positive number; the sign comes from `type`.
        type: One of 'income', 'expense', 'transfer'.
        description: Free-text payee or memo.
        date: ISO date (YYYY-MM-DD). Defaults to today.
        category: Existing category name. Errors if the category doesn't exist.
        account: Existing account nickname. Errors if the account doesn't exist.
        is_test: Mark as a test/throwaway row. Hidden from list/summary by default.
    """
    with session_scope() as s:
        try:
            tt = s.query(TransactionType).filter_by(name=type).one()
        except NoResultFound:
            return f"unknown transaction type {type!r}; expected income/expense/transfer."

        cat = None
        if category is not None:
            matches = s.query(Category).filter_by(name=category, type_id=tt.id).all()
            if not matches:
                return (
                    f"no {type} category named {category!r}; "
                    f"add it first with add_category."
                )
            if len(matches) > 1:
                return (
                    f"category {category!r} is ambiguous ({len(matches)} matches); "
                    f"specify a different name."
                )
            cat = matches[0]

        acct = None
        if account is not None:
            acct = s.query(Account).filter_by(nickname=account).first()
            if acct is None:
                return (
                    f"no account with nickname {account!r}; "
                    f"add it first with add_account."
                )

        tx = Transaction(
            date=_parse_date(date),
            amount=_parse_amount(amount),
            type=tt,
            category=cat,
            account=acct,
            description=description,
            is_test=is_test,
        )
        s.add(tx)
        s.flush()
        marker = " [TEST]" if is_test else ""
        return (
            f"recorded transaction #{tx.id}{marker}: {tx.date} {type} "
            f"${tx.amount} ({description!r})"
        )


@tool
def list_transactions(
    limit: int = 10,
    since_date: str | None = None,
    category: str | None = None,
    account: str | None = None,
    include_test: bool = False,
) -> list[dict[str, Any]]:
    """List recent transactions, newest first.

    Args:
        limit: Max rows to return.
        since_date: ISO date; include only transactions on or after this date.
        category: Filter by category name.
        account: Filter by account nickname.
        include_test: If False (default), hide rows flagged is_test=True.
    """
    with session_scope() as s:
        q = s.query(Transaction)
        if not include_test:
            q = q.filter(Transaction.is_test.is_(False))
        if since_date is not None:
            q = q.filter(Transaction.date >= _parse_date(since_date))
        if category is not None:
            q = q.join(Transaction.category).filter(Category.name == category)
        if account is not None:
            q = q.join(Transaction.account).filter(Account.nickname == account)
        rows = (
            q.order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": tx.id,
                "date": tx.date.isoformat(),
                "amount": str(tx.amount),
                "type": tx.type.name,
                "category": tx.category.name if tx.category else None,
                "account": tx.account.nickname if tx.account else None,
                "description": tx.description,
                "is_test": tx.is_test,
            }
            for tx in rows
        ]


@tool
def summarize_transactions(
    start_date: str,
    end_date: str,
    group_by: str | None = None,
    include_test: bool = False,
) -> dict[str, Any]:
    """Summarize transactions over a date range (inclusive). Totals are signed.

    Args:
        start_date: ISO date.
        end_date: ISO date.
        group_by: One of 'category', 'account', 'type', or None for overall total.
        include_test: If False (default), exclude rows flagged is_test=True.
    """
    valid = (None, "category", "account", "type")
    if group_by not in valid:
        return {"error": f"group_by must be one of {valid}, got {group_by!r}"}

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    signed = Transaction.amount * TransactionType.sign

    with session_scope() as s:
        base = (
            s.query(Transaction)
            .join(Transaction.type)
            .filter(Transaction.date >= start, Transaction.date <= end)
        )
        if not include_test:
            base = base.filter(Transaction.is_test.is_(False))

        if group_by is None:
            total = base.with_entities(sa_func.sum(signed)).scalar() or Decimal("0")
            return {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "net": str(total),
            }

        if group_by == "type":
            rows = (
                base.with_entities(TransactionType.name, sa_func.sum(signed))
                .group_by(TransactionType.name)
                .all()
            )
        elif group_by == "category":
            rows = (
                base.outerjoin(Transaction.category)
                .with_entities(Category.name, sa_func.sum(signed))
                .group_by(Category.name)
                .all()
            )
        else:  # account
            rows = (
                base.outerjoin(Transaction.account)
                .with_entities(Account.nickname, sa_func.sum(signed))
                .group_by(Account.nickname)
                .all()
            )

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "group_by": group_by,
            "groups": [{"key": k or "(none)", "net": str(v)} for k, v in rows],
        }


@tool
def add_account(
    nickname: str,
    bank_name: str,
    account_type: str,
    last_four: str | None = None,
) -> str:
    """Add a new bank account.

    Args:
        nickname: Short label used as the natural lookup key (e.g. 'chase checking').
        bank_name: e.g. 'Chase'. Use 'Cash' for cash accounts.
        account_type: One of 'checking', 'savings', 'investment', 'credit_card', 'cash'.
        last_four: Last 4 digits of the account number (string preserves leading zeros).
    """
    if last_four is not None and (not last_four.isdigit() or len(last_four) > 4):
        return f"last_four must be up to 4 digits; got {last_four!r}."

    with session_scope() as s:
        try:
            at = s.query(AccountType).filter_by(name=account_type).one()
        except NoResultFound:
            valid = [t.name for t in s.query(AccountType).order_by(AccountType.id).all()]
            return f"unknown account_type {account_type!r}; expected one of {valid}."

        if s.query(Account).filter_by(nickname=nickname).first() is not None:
            return f"account nickname {nickname!r} already exists."

        acct = Account(
            nickname=nickname,
            bank_name=bank_name,
            account_type=at,
            last_four=last_four,
        )
        s.add(acct)
        s.flush()
        return f"added account #{acct.id} ({nickname}, {bank_name}, {account_type})"


@tool
def add_category(
    name: str,
    type: str,
    parent: str | None = None,
) -> str:
    """Add a new transaction category, optionally nested under a parent.

    Args:
        name: Category name (e.g. 'food', 'groceries').
        type: One of 'income', 'expense', 'transfer'.
        parent: Optional name of an existing parent category (must share the same `type`).
    """
    with session_scope() as s:
        try:
            tt = s.query(TransactionType).filter_by(name=type).one()
        except NoResultFound:
            return f"unknown transaction type {type!r}; expected income/expense/transfer."

        parent_cat = None
        if parent is not None:
            parent_matches = (
                s.query(Category).filter_by(name=parent, type_id=tt.id).all()
            )
            if not parent_matches:
                return f"no {type} category named {parent!r} to use as parent."
            if len(parent_matches) > 1:
                return f"parent {parent!r} is ambiguous ({len(parent_matches)} matches)."
            parent_cat = parent_matches[0]

        try:
            cat = Category(name=name, type=tt, parent=parent_cat)
            s.add(cat)
            s.flush()
        except ValueError as e:
            return f"could not add category: {e}"

        path = f"{parent}/{name}" if parent else name
        return f"added category #{cat.id} ({type}: {path})"


TOOLS = [
    record_transaction,
    list_transactions,
    summarize_transactions,
    add_account,
    add_category,
]
