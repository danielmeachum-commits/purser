"""LangChain tools exposed to the agent for managing transactions."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy.exc import NoResultFound

from agent.dates import resolve_range
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


_PERIOD_FORMATS = {
    "day": "%Y-%m-%d", "1d": "%Y-%m-%d",
    "week": "%Y-W%W", "1w": "%Y-W%W",
    "month": "%Y-%m", "1m": "%Y-%m",
    "year": "%Y", "1y": "%Y",
}

_TEST_MODES = ("exclude", "only", "include")


def _apply_test_mode(query: Any, test_mode: str) -> Any:
    if test_mode == "exclude":
        return query.filter(Transaction.is_test.is_(False))
    if test_mode == "only":
        return query.filter(Transaction.is_test.is_(True))
    return query


def _normalize_group_by(group_by: str | list[str] | None) -> list[str] | dict[str, str]:
    """Coerce group_by to a list of dim names. Returns an error dict on bad input."""
    valid = {"category", "account", "type"}
    if group_by is None:
        return []
    if isinstance(group_by, str):
        text = group_by.strip().lower()
        if text in ("", "none"):
            return []
        items = [d.strip() for d in text.split(",") if d.strip()]
    elif isinstance(group_by, list):
        items = [d.strip().lower() for d in group_by if d and d.strip()]
    else:
        return {"error": f"group_by must be a string, list, or None; got {type(group_by).__name__}"}
    bad = [d for d in items if d not in valid]
    if bad:
        return {"error": f"group_by values must be in {sorted(valid)}; got {bad!r}"}
    seen: list[str] = []
    for d in items:
        if d not in seen:
            seen.append(d)
    return seen


def _resolve_window(
    date_range: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[date_type, date_type] | dict[str, str]:
    """Return (start, end) or a {'error': ...} dict for the caller to surface."""
    if date_range is not None:
        if start_date is not None or end_date is not None:
            return {"error": "pass either date_range or start_date+end_date, not both"}
        try:
            return resolve_range(date_range)
        except ValueError as e:
            return {"error": str(e)}
    if start_date is None or end_date is None:
        return {"error": "provide date_range, or both start_date and end_date"}
    return _parse_date(start_date), _parse_date(end_date)


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
    if test_mode not in _TEST_MODES:
        return {"error": f"test_mode must be one of {_TEST_MODES}, got {test_mode!r}"}
    if date_range is not None and since_date is not None:
        return {"error": "pass either date_range or since_date, not both"}
    range_window: tuple[date_type, date_type] | None = None
    if date_range is not None:
        try:
            range_window = resolve_range(date_range)
        except ValueError as e:
            return {"error": str(e)}

    with session_scope() as s:
        q = _apply_test_mode(s.query(Transaction), test_mode)
        if range_window is not None:
            q = q.filter(
                Transaction.date >= range_window[0],
                Transaction.date <= range_window[1],
            )
        elif since_date is not None:
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


def _new_acc(extended: bool) -> dict[str, Any]:
    acc: dict[str, Any] = {
        "net": Decimal("0"),
        "inflow": Decimal("0"),
        "outflow": Decimal("0"),
        "count": 0,
    }
    if extended:
        acc["_amounts"] = []
        acc["_largest"] = None
    return acc


def _add_to_acc(acc: dict[str, Any], row: Any, extended: bool) -> None:
    amount = row.amount
    signed = amount * row.sign
    acc["net"] += signed
    if signed > 0:
        acc["inflow"] += signed
    elif signed < 0:
        acc["outflow"] += signed
    acc["count"] += 1
    if extended:
        acc["_amounts"].append(amount)
        if acc["_largest"] is None or amount > acc["_largest"]["amount"]:
            acc["_largest"] = {
                "amount": amount,
                "id": row.id,
                "description": row.description,
            }


def _finalize_acc(acc: dict[str, Any], extended: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "net": str(acc["net"]),
        "inflow": str(acc["inflow"]),
        "outflow": str(acc["outflow"]),
        "count": acc["count"],
    }
    if extended and acc["count"]:
        amounts = acc["_amounts"]
        avg = (sum(amounts) / Decimal(len(amounts))).quantize(Decimal("0.01"))
        out["avg"] = str(avg)
        out["min"] = str(min(amounts))
        out["max"] = str(max(amounts))
        largest = acc["_largest"]
        out["largest"] = {
            "id": largest["id"],
            "amount": str(largest["amount"]),
            "description": largest["description"],
        }
    return out


def _row_dim(row: Any, dim: str) -> str:
    val = {
        "category": row.category_name,
        "account": row.account_nickname,
        "type": row.type_name,
    }[dim]
    return val or "(none)"


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
    dims = _normalize_group_by(group_by)
    if isinstance(dims, dict):
        return dims
    if period is not None and period not in _PERIOD_FORMATS:
        return {
            "error": f"period must be one of {sorted(_PERIOD_FORMATS)}, got {period!r}"
        }
    if test_mode not in _TEST_MODES:
        return {"error": f"test_mode must be one of {_TEST_MODES}, got {test_mode!r}"}

    window = _resolve_window(date_range, start_date, end_date)
    if isinstance(window, dict):
        return window
    start, end = window

    period_fmt = _PERIOD_FORMATS[period] if period else None

    with session_scope() as s:
        rows = (
            s.query(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.description,
                Transaction.is_test,
                TransactionType.sign.label("sign"),
                TransactionType.name.label("type_name"),
                Category.name.label("category_name"),
                Account.nickname.label("account_nickname"),
            )
            .join(Transaction.type)
            .outerjoin(Transaction.category)
            .outerjoin(Transaction.account)
            .filter(Transaction.date >= start, Transaction.date <= end)
        )
        rows = _apply_test_mode(rows, test_mode).all()

        overall = _new_acc(extended_metrics)
        bucket_accs: dict[str, dict[str, Any]] = {}
        bucket_group_accs: dict[str, dict[tuple, dict[str, Any]]] = {}
        group_accs: dict[tuple, dict[str, Any]] = {}

        for row in rows:
            _add_to_acc(overall, row, extended_metrics)
            pk = row.date.strftime(period_fmt) if period_fmt else None
            dk = tuple(_row_dim(row, d) for d in dims)
            if period and dims:
                b = bucket_accs.setdefault(pk, _new_acc(extended_metrics))
                _add_to_acc(b, row, extended_metrics)
                gmap = bucket_group_accs.setdefault(pk, {})
                g = gmap.setdefault(dk, _new_acc(extended_metrics))
                _add_to_acc(g, row, extended_metrics)
            elif period:
                b = bucket_accs.setdefault(pk, _new_acc(extended_metrics))
                _add_to_acc(b, row, extended_metrics)
            elif dims:
                g = group_accs.setdefault(dk, _new_acc(extended_metrics))
                _add_to_acc(g, row, extended_metrics)

        meta: dict[str, Any] = {"start": start.isoformat(), "end": end.isoformat()}
        if period is not None:
            meta["period"] = period
        if dims:
            meta["group_by"] = dims[0] if len(dims) == 1 else dims
        if test_mode != "exclude":
            meta["test_mode"] = test_mode

        def key_to_value(dk: tuple) -> Any:
            if len(dims) == 1:
                return dk[0]
            return {d: v for d, v in zip(dims, dk)}

        result: dict[str, Any] = {**meta, **_finalize_acc(overall, extended_metrics)}

        if period and dims:
            buckets = []
            for pk in sorted(bucket_accs):
                bucket_obj: dict[str, Any] = {
                    "period": pk,
                    **_finalize_acc(bucket_accs[pk], extended_metrics),
                    "groups": [
                        {"key": key_to_value(dk), **_finalize_acc(g, extended_metrics)}
                        for dk, g in sorted(bucket_group_accs[pk].items())
                    ],
                }
                buckets.append(bucket_obj)
            result["buckets"] = buckets
        elif period:
            result["buckets"] = [
                {"period": pk, **_finalize_acc(bucket_accs[pk], extended_metrics)}
                for pk in sorted(bucket_accs)
            ]
        elif dims:
            result["groups"] = [
                {"key": key_to_value(dk), **_finalize_acc(g, extended_metrics)}
                for dk, g in sorted(group_accs.items())
            ]

        if include_transactions:
            result["transactions"] = [
                {
                    "id": row.id,
                    "date": row.date.isoformat(),
                    "amount": str(row.amount),
                    "type": row.type_name,
                    "category": row.category_name,
                    "account": row.account_nickname,
                    "description": row.description,
                    "is_test": row.is_test,
                }
                for row in sorted(rows, key=lambda r: (r.date, r.id), reverse=True)
            ]
        return result


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
