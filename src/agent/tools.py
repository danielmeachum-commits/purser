"""LangChain tools exposed to the agent for managing transactions."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy.exc import NoResultFound

from agent import queries
from agent.db import (
    Account,
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


_AFFIRMATIVE = {"yes", "y", "confirm", "ok", "okay", "sure", "go", "do it"}


def _is_affirmative(answer: Any) -> bool:
    """Best-effort yes/no parsing of an interrupt resume value."""
    if isinstance(answer, bool):
        return answer
    if isinstance(answer, dict):
        for key in ("confirm", "approved", "answer", "response"):
            if key in answer:
                return _is_affirmative(answer[key])
        return False
    if isinstance(answer, str):
        return answer.strip().lower() in _AFFIRMATIVE
    return False


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
    parsed_date = _parse_date(date)
    parsed_amount = _parse_amount(amount)

    with session_scope() as s:
        try:
            tt = s.query(TransactionType).filter_by(name=type).one()
        except NoResultFound:
            return f"unknown transaction type {type!r}; expected income/expense/transfer."

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

        if account is not None:
            if s.query(Account).filter_by(nickname=account).first() is None:
                return (
                    f"no account with nickname {account!r}; "
                    f"add it first with add_account."
                )

    preview = {
        "action": "record_transaction",
        "transaction": {
            "date": parsed_date.isoformat(),
            "type": type,
            "amount": str(parsed_amount),
            "description": description,
            "category": category,
            "account": account,
            "is_test": is_test,
        },
        "prompt": "Record this transaction? Reply 'yes' to confirm or 'no' to cancel.",
    }
    answer = interrupt(preview)
    if not _is_affirmative(answer):
        return f"transaction not recorded — user declined (response: {answer!r})."

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
        marker = " [TEST]" if is_test else ""
        return (
            f"recorded transaction #{tx.id}{marker}: {tx.date} {type} "
            f"${tx.amount} ({description!r})"
        )


@tool
def list_transactions(
    limit: int = 10,
    date_range: str | None = None,
    since_date: str | None = None,
    category: str | None = None,
    account: str | None = None,
    test_mode: str = "exclude",
) -> list[dict[str, Any]] | dict[str, str]:
    """List recent transactions, newest first.

    Args:
        limit: Max rows to return.
        date_range: Natural-language window such as 'last month', 'this week',
            'june 2025', 'ytd', or an ISO range '2026-06-01 to 2026-06-30'.
            Mutually exclusive with since_date.
        since_date: ISO date; include only transactions on or after this date.
        category: Filter by category name.
        account: Filter by account nickname.
        test_mode: 'exclude' (default) hides rows flagged is_test=True;
            'only' returns only those rows; 'include' returns both.
    """
    return queries.list_transactions(
        limit=limit,
        date_range=date_range,
        since_date=since_date,
        category=category,
        account=account,
        test_mode=test_mode,
    )


@tool
def summarize_transactions(
    date_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    group_by: str | list[str] | None = "category",
    include_transactions: bool = False,
    extended_metrics: bool = False,
    test_mode: str = "exclude",
) -> dict[str, Any]:
    """Summarize transactions over a date range (inclusive). Totals are signed.

    Each result level reports `net`, `inflow`, `outflow`, and `count`.
    Set `extended_metrics=True` to also include `avg`, `min`, `max`, and
    `largest: {id, amount, description}` per group/bucket.

    Args:
        date_range: Natural-language window such as 'last month', 'this week',
            'june 2025', 'last 30 days', 'ytd', 'in 2024', or an ISO range
            like '2026-06-01 to 2026-06-30'. Mutually exclusive with
            start_date+end_date.
        start_date: ISO date. Use with end_date if date_range is omitted.
        end_date: ISO date. Use with start_date if date_range is omitted.
        period: Optional time bucket — 'day', 'week', 'month', or 'year'
            (also '1d'/'1w'/'1m'/'1y'). When set, results are grouped into
            buckets; combine with group_by to sub-group within each bucket.
        group_by: Dimension(s) to group by. Pass a single name ('category',
            'account', 'type'), a list like ['category','account'], 'none'
            (or None) for a single total, or a comma-separated string.
            Defaults to 'category'.
        include_transactions: If True, append the raw matching rows under
            a 'transactions' key — useful when you want totals AND the
            rows behind them in one call.
        extended_metrics: If True, include avg/min/max/largest in addition
            to the base net/inflow/outflow/count.
        test_mode: 'exclude' (default) hides rows flagged is_test=True;
            'only' returns only those rows; 'include' returns both.
    """
    return queries.summarize_transactions(
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
        period=period,
        group_by=group_by,
        include_transactions=include_transactions,
        extended_metrics=extended_metrics,
        test_mode=test_mode,
    )


@tool
def list_categories(
    type: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List existing categories, optionally filtered by transaction type.

    Use this before recording a transaction to find a category that
    matches the payee/memo, or to decide whether to propose a new
    category (top-level or as a subcategory of an existing one).

    Args:
        type: Filter to 'income', 'expense', or 'transfer'. None returns all.
        include_inactive: If False (default), only return active categories.
    """
    return queries.list_categories(type=type, include_inactive=include_inactive)


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
    list_categories,
    add_account,
    add_category,
]
