"""Reusable transaction queries shared by the LangGraph tools and the API.

These return plain dicts/lists — no @tool decorator — so callers can use
them from FastAPI routes, MCP handlers, the agent, or tests without the
LangChain shim. The agent's `tools.py` wraps these for the LLM.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from agent.dates import resolve_range
from agent.db import (
    Account,
    AccountType,
    Category,
    SavingsGoal,
    Transaction,
    TransactionType,
    session_scope,
)

PERIOD_FORMATS = {
    "day": "%Y-%m-%d", "1d": "%Y-%m-%d",
    "week": "%Y-W%W", "1w": "%Y-W%W",
    "month": "%Y-%m", "1m": "%Y-%m",
    "year": "%Y", "1y": "%Y",
}

TEST_MODES = ("exclude", "only", "include")

_VALID_DIMS = {"category", "account", "type"}


def _parse_date(s: str | None) -> date_type:
    if s is None:
        return date_type.today()
    return date_type.fromisoformat(s)


def _apply_test_mode(query: Any, test_mode: str) -> Any:
    if test_mode == "exclude":
        return query.filter(Transaction.is_test.is_(False))
    if test_mode == "only":
        return query.filter(Transaction.is_test.is_(True))
    return query


def _normalize_group_by(
    group_by: str | list[str] | None,
) -> list[str] | dict[str, str]:
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
        return {
            "error": f"group_by must be a string, list, or None; got {type(group_by).__name__}"
        }
    bad = [d for d in items if d not in _VALID_DIMS]
    if bad:
        return {
            "error": f"group_by values must be in {sorted(_VALID_DIMS)}; got {bad!r}"
        }
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


def _serialize_tx(tx: Transaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "date": tx.date.isoformat(),
        "amount": str(tx.amount),
        "type": tx.type.name,
        "category": tx.category.name if tx.category else None,
        "account": tx.account.nickname if tx.account else None,
        "description": tx.description,
        "is_test": tx.is_test,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


# --- public read functions -------------------------------------------------


def list_transactions(
    *,
    limit: int = 50,
    date_range: str | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
    category: str | None = None,
    account: str | None = None,
    type: str | None = None,
    test_mode: str = "exclude",
) -> list[dict[str, Any]] | dict[str, str]:
    """List transactions newest-first. Returns rows or {'error': ...}."""
    if test_mode not in TEST_MODES:
        return {"error": f"test_mode must be one of {TEST_MODES}, got {test_mode!r}"}
    if date_range is not None and (since_date is not None or until_date is not None):
        return {"error": "pass either date_range or since_date/until_date, not both"}

    window: tuple[date_type, date_type] | None = None
    if date_range is not None:
        try:
            window = resolve_range(date_range)
        except ValueError as e:
            return {"error": str(e)}

    with session_scope() as s:
        q = _apply_test_mode(s.query(Transaction), test_mode)
        if window is not None:
            q = q.filter(Transaction.date >= window[0], Transaction.date <= window[1])
        else:
            if since_date is not None:
                q = q.filter(Transaction.date >= _parse_date(since_date))
            if until_date is not None:
                q = q.filter(Transaction.date <= _parse_date(until_date))
        if category is not None:
            q = q.join(Transaction.category).filter(Category.name == category)
        if account is not None:
            q = q.join(Transaction.account).filter(Account.nickname == account)
        if type is not None:
            q = q.join(Transaction.type).filter(TransactionType.name == type)
        rows = (
            q.order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(limit)
            .all()
        )
        return [_serialize_tx(tx) for tx in rows]


def get_transaction(tx_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        tx = s.get(Transaction, tx_id)
        return _serialize_tx(tx) if tx else None


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


def summarize_transactions(
    *,
    date_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    group_by: str | list[str] | None = "category",
    include_transactions: bool = False,
    extended_metrics: bool = False,
    test_mode: str = "exclude",
) -> dict[str, Any]:
    """Aggregate signed totals. See CLAUDE.md for the output shape."""
    dims = _normalize_group_by(group_by)
    if isinstance(dims, dict):
        return dims
    if period is not None and period not in PERIOD_FORMATS:
        return {
            "error": f"period must be one of {sorted(PERIOD_FORMATS)}, got {period!r}"
        }
    if test_mode not in TEST_MODES:
        return {"error": f"test_mode must be one of {TEST_MODES}, got {test_mode!r}"}

    window = _resolve_window(date_range, start_date, end_date)
    if isinstance(window, dict):
        return window
    start, end = window
    period_fmt = PERIOD_FORMATS[period] if period else None

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


def list_categories(
    *, type: str | None = None, include_inactive: bool = False
) -> list[dict[str, Any]]:
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
        return [_serialize_category(c) for c in rows]


def _serialize_category(c: Category) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "type": c.type.name,
        "parent": c.parent.name if c.parent else None,
        "parent_id": c.parent_id,
        "is_active": c.is_active,
        "monthly_budget": str(c.monthly_budget) if c.monthly_budget is not None else None,
        "target_amount": str(c.target_amount) if c.target_amount is not None else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_savings_goal(g: SavingsGoal) -> dict[str, Any]:
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": str(g.target_amount),
        "allocated_amount": str(g.allocated_amount),
        "account": g.account.nickname if g.account else None,
        "account_id": g.account_id,
        "notes": g.notes,
        "is_active": g.is_active,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def list_savings_goals(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    """List savings goals, ordered by name."""
    with session_scope() as s:
        q = s.query(SavingsGoal)
        if not include_inactive:
            q = q.filter(SavingsGoal.is_active.is_(True))
        return [_serialize_savings_goal(g) for g in q.order_by(SavingsGoal.name).all()]


def category_breakdown(
    *,
    date_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    test_mode: str = "exclude",
) -> dict[str, Any]:
    """Per-category direct totals for the window, keyed by category id.

    Returns every active category (so the dashboard can show zero rows for
    budgeted-but-unused categories), with parent_id, budget fields, and
    the direct net/count over the requested window. Rollup totals are the
    client's job — names alone aren't unique enough to nest safely.
    """
    if test_mode not in TEST_MODES:
        return {"error": f"test_mode must be one of {TEST_MODES}, got {test_mode!r}"}
    window = _resolve_window(date_range, start_date, end_date)
    if isinstance(window, dict):
        return window
    start, end = window

    with session_scope() as s:
        cats = (
            s.query(Category)
            .filter(Category.is_active.is_(True))
            .order_by(Category.type_id, Category.parent_id.is_(None).desc(), Category.name)
            .all()
        )
        rows = (
            s.query(
                Transaction.category_id,
                Transaction.amount,
                TransactionType.sign,
            )
            .join(Transaction.type)
            .filter(Transaction.date >= start, Transaction.date <= end)
        )
        rows = _apply_test_mode(rows, test_mode).all()

        direct: dict[int, dict[str, Any]] = {}
        for cat_id, amount, sign in rows:
            if cat_id is None:
                continue
            acc = direct.setdefault(
                cat_id, {"net": Decimal("0"), "count": 0}
            )
            acc["net"] += amount * sign
            acc["count"] += 1

        categories = []
        for c in cats:
            acc = direct.get(c.id, {"net": Decimal("0"), "count": 0})
            categories.append({
                "id": c.id,
                "name": c.name,
                "type": c.type.name,
                "parent_id": c.parent_id,
                "monthly_budget": (
                    str(c.monthly_budget) if c.monthly_budget is not None else None
                ),
                "target_amount": (
                    str(c.target_amount) if c.target_amount is not None else None
                ),
                "direct_net": str(acc["net"]),
                "direct_count": acc["count"],
            })

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "categories": categories,
        }


def _serialize_account(a: Account) -> dict[str, Any]:
    return {
        "id": a.id,
        "nickname": a.nickname,
        "bank_name": a.bank_name,
        "account_type": a.account_type.name,
        "last_four": a.last_four,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def list_accounts(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Account)
        if not include_inactive:
            q = q.filter(Account.is_active.is_(True))
        rows = q.order_by(Account.nickname).all()
        return [_serialize_account(a) for a in rows]


def list_account_types() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.query(AccountType).order_by(AccountType.id).all()
        return [{"id": r.id, "name": r.name} for r in rows]


def list_transaction_types() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.query(TransactionType).order_by(TransactionType.id).all()
        return [{"id": r.id, "name": r.name, "sign": r.sign} for r in rows]


# Re-exports used by callers that want raw session access alongside.
__all__ = [
    "PERIOD_FORMATS",
    "TEST_MODES",
    "Session",
    "category_breakdown",
    "get_transaction",
    "list_account_types",
    "list_accounts",
    "list_categories",
    "list_savings_goals",
    "list_transaction_types",
    "list_transactions",
    "summarize_transactions",
]
