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


_AFFIRMATIVE = {"yes", "y", "confirm", "ok", "okay", "sure", "go", "do it", "true"}

_EDIT_FIELDS = (
    "date",
    "type",
    "amount",
    "description",
    "category",
    "account",
    "is_test",
)


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


def _extract_edits(answer: Any) -> dict[str, Any]:
    """Pull override fields out of a resume payload.

    Returns a dict containing only the keys the user supplied (any of
    `_EDIT_FIELDS`). For non-dict resume values, returns an empty dict.
    Empty strings for `category` / `account` are preserved as a signal
    that the caller wants to clear those fields.
    """
    if not isinstance(answer, dict):
        return {}
    edits: dict[str, Any] = {}
    for key in _EDIT_FIELDS:
        if key in answer:
            edits[key] = answer[key]
    return edits


def _validate_proposed(
    s: Any,
    *,
    type_name: str,
    category: str | None,
    account: str | None,
) -> str | None:
    """Validate a proposed type/category/account triple against the DB.

    Returns an error string on failure, or None if the proposal is valid.
    Performs all lookups in the given session.
    """
    try:
        tt = s.query(TransactionType).filter_by(name=type_name).one()
    except NoResultFound:
        return f"unknown transaction type {type_name!r}; expected income/expense/transfer."

    if category is not None and category != "":
        matches = s.query(Category).filter_by(name=category, type_id=tt.id).all()
        if not matches:
            return (
                f"no {type_name} category named {category!r}; "
                f"add it first with add_category."
            )
        if len(matches) > 1:
            return (
                f"category {category!r} is ambiguous ({len(matches)} matches); "
                f"specify a different name."
            )

    if account is not None and account != "":
        if s.query(Account).filter_by(nickname=account).first() is None:
            return (
                f"no account with nickname {account!r}; "
                f"add it first with add_account."
            )
    return None


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
        err = _validate_proposed(
            s, type_name=type, category=category, account=account
        )
        if err is not None:
            return err

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

    # Merge any edits the user supplied on resume. Keys absent from the
    # resume payload fall through to the originally proposed values; empty
    # strings for category/account mean "clear that field".
    edits = _extract_edits(answer)
    final_type = edits["type"] if "type" in edits and edits["type"] is not None else type
    final_description = (
        edits["description"]
        if "description" in edits and edits["description"] is not None
        else description
    )
    final_is_test = bool(
        edits["is_test"]
        if "is_test" in edits and edits["is_test"] is not None
        else is_test
    )

    if "date" in edits and edits["date"] is not None and edits["date"] != "":
        try:
            final_date = _parse_date(str(edits["date"]))
        except ValueError:
            return f"invalid date: {edits['date']!r} (expected YYYY-MM-DD)."
    else:
        final_date = parsed_date

    if "amount" in edits and edits["amount"] is not None and edits["amount"] != "":
        try:
            final_amount = _parse_amount(edits["amount"])
        except ValueError as e:
            return str(e)
    else:
        final_amount = parsed_amount
    if final_amount <= 0:
        return f"invalid amount: {final_amount} (must be greater than 0)."

    # For category/account, an empty string is meaningful ("none"); only
    # missing keys fall through to the originals.
    if "category" in edits:
        raw_cat = edits["category"]
        final_category: str | None = None if raw_cat in (None, "") else str(raw_cat)
    else:
        final_category = category
    if "account" in edits:
        raw_acct = edits["account"]
        final_account: str | None = None if raw_acct in (None, "") else str(raw_acct)
    else:
        final_account = account

    with session_scope() as s:
        err = _validate_proposed(
            s,
            type_name=final_type,
            category=final_category,
            account=final_account,
        )
        if err is not None:
            return err
        tt = s.query(TransactionType).filter_by(name=final_type).one()
        cat = (
            s.query(Category).filter_by(name=final_category, type_id=tt.id).one()
            if final_category is not None
            else None
        )
        acct = (
            s.query(Account).filter_by(nickname=final_account).one()
            if final_account is not None
            else None
        )
        tx = Transaction(
            date=final_date,
            amount=final_amount,
            type=tt,
            category=cat,
            account=acct,
            description=final_description,
            is_test=final_is_test,
        )
        s.add(tx)
        s.flush()
        marker = " [TEST]" if final_is_test else ""
        return (
            f"recorded transaction #{tx.id}{marker}: {tx.date} {final_type} "
            f"${tx.amount} ({final_description!r})"
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
