"""MCP server exposing budget-graph DB operations to local MCP clients.

Run via the `budget-mcp` console script (registered in pyproject.toml)
or `python -m agent.mcp_server`. Uses stdio transport — clients spawn
this process and talk JSON-RPC over its stdin/stdout.

Confirmation flow for writes: `record_transaction` returns a preview
and refuses to write unless called with `confirm=True`. The MCP client
(e.g. Claude Code) is responsible for showing the preview to the user
and only re-calling with `confirm=True` after they say yes. This is the
MCP analogue of the `interrupt()` flow in `agent.tools`.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server.fastmcp import FastMCP
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

mcp = FastMCP("budget-graph")


def _parse_date(s: str | None) -> date_type:
    return date_type.today() if s is None else date_type.fromisoformat(s)


def _parse_amount(amount: float | int | str) -> Decimal:
    try:
        return Decimal(str(amount))
    except InvalidOperation as e:
        raise ValueError(f"invalid amount: {amount!r}") from e


@mcp.tool()
def list_categories(
    type: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List existing categories, optionally filtered by transaction type.

    Args:
        type: Filter to 'income', 'expense', or 'transfer'. None returns all.
        include_inactive: If False (default), only return active categories.
    """
    with session_scope() as s:
        q = s.query(Category)
        if not include_inactive:
            q = q.filter(Category.is_active.is_(True))
        if type is not None:
            try:
                tt = s.query(TransactionType).filter_by(name=type).one()
            except NoResultFound:
                return []
            q = q.filter(Category.type_id == tt.id)
        rows = q.order_by(Category.type_id, Category.name).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type.name,
                "parent": c.parent.name if c.parent else None,
                "is_active": c.is_active,
            }
            for c in rows
        ]


@mcp.tool()
def list_accounts(include_inactive: bool = False) -> list[dict[str, Any]]:
    """List bank accounts.

    Args:
        include_inactive: If False (default), only return active accounts.
    """
    with session_scope() as s:
        q = s.query(Account)
        if not include_inactive:
            q = q.filter(Account.is_active.is_(True))
        return [
            {
                "id": a.id,
                "nickname": a.nickname,
                "bank_name": a.bank_name,
                "account_type": a.account_type.name,
                "last_four": a.last_four,
                "is_active": a.is_active,
            }
            for a in q.order_by(Account.nickname).all()
        ]


@mcp.tool()
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


@mcp.tool()
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
            return {"start": start.isoformat(), "end": end.isoformat(), "net": str(total)}

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
        else:
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


@mcp.tool()
def record_transaction(
    amount: float,
    type: str,
    description: str,
    date: str | None = None,
    category: str | None = None,
    account: str | None = None,
    is_test: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Record a single financial transaction. Two-step confirm flow.

    When `confirm=False` (default), validates inputs and returns a preview
    without writing. Show the preview to the user; only call again with
    `confirm=True` after they explicitly agree.

    Args:
        amount: Positive number; the sign comes from `type`.
        type: One of 'income', 'expense', 'transfer'.
        description: Free-text payee or memo.
        date: ISO date (YYYY-MM-DD). Defaults to today.
        category: Existing category name. Errors if it doesn't exist.
        account: Existing account nickname. Errors if it doesn't exist.
        is_test: Mark as a test/throwaway row.
        confirm: Set True ONLY after the user approves the preview.
    """
    try:
        parsed_date = _parse_date(date)
        parsed_amount = _parse_amount(amount)
    except (ValueError, TypeError) as e:
        return {"status": "error", "message": str(e)}

    with session_scope() as s:
        try:
            tt = s.query(TransactionType).filter_by(name=type).one()
        except NoResultFound:
            return {
                "status": "error",
                "message": f"unknown transaction type {type!r}; expected income/expense/transfer.",
            }

        if category is not None:
            matches = s.query(Category).filter_by(name=category, type_id=tt.id).all()
            if not matches:
                return {
                    "status": "error",
                    "message": f"no {type} category named {category!r}; add it first with add_category.",
                }
            if len(matches) > 1:
                return {
                    "status": "error",
                    "message": f"category {category!r} is ambiguous ({len(matches)} matches).",
                }

        if account is not None:
            if s.query(Account).filter_by(nickname=account).first() is None:
                return {
                    "status": "error",
                    "message": f"no account with nickname {account!r}; add it first with add_account.",
                }

    preview = {
        "date": parsed_date.isoformat(),
        "type": type,
        "amount": str(parsed_amount),
        "description": description,
        "category": category,
        "account": account,
        "is_test": is_test,
    }

    if not confirm:
        return {
            "status": "needs_confirmation",
            "transaction": preview,
            "next": "Show this preview to the user. Only call record_transaction again with confirm=True after they explicitly approve.",
        }

    with session_scope() as s:
        tt = s.query(TransactionType).filter_by(name=type).one()
        cat = (
            s.query(Category).filter_by(name=category, type_id=tt.id).one()
            if category is not None
            else None
        )
        acct = (
            s.query(Account).filter_by(nickname=account).one()
            if account is not None
            else None
        )
        tx = Transaction(
            date=parsed_date,
            amount=parsed_amount,
            type=tt,
            category=cat,
            account=acct,
            description=description,
            is_test=is_test,
        )
        s.add(tx)
        s.flush()
        return {"status": "recorded", "id": tx.id, "transaction": preview}


@mcp.tool()
def add_account(
    nickname: str,
    bank_name: str,
    account_type: str,
    last_four: str | None = None,
) -> str:
    """Add a new bank account.

    Args:
        nickname: Short label (e.g. 'chase checking').
        bank_name: e.g. 'Chase'. Use 'Cash' for cash accounts.
        account_type: One of 'checking', 'savings', 'investment', 'credit_card', 'cash'.
        last_four: Last 4 digits (string preserves leading zeros).
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


@mcp.tool()
def add_category(
    name: str,
    type: str,
    parent: str | None = None,
) -> str:
    """Add a new transaction category, optionally nested under a parent.

    Args:
        name: Category name (e.g. 'food', 'groceries').
        type: One of 'income', 'expense', 'transfer'.
        parent: Optional name of an existing parent category (same type).
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


def main() -> None:
    """Entry point for the `budget-mcp` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
