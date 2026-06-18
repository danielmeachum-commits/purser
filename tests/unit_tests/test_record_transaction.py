"""Unit tests for `record_transaction` interrupt/edit flow.

Covers the resume-with-edits path that lets the user override fields on the
proposed transaction before it's written.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent import tools
from agent.db import database as db_mod
from agent.db.models import Account, AccountType, Base, Category, TransactionType


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch):
    """Swap the global SessionLocal/engine to a fresh in-memory SQLite."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", TestSession)

    # Seed lookups + a sample account and category.
    with TestSession() as s:
        income = TransactionType(name="income", sign=1)
        expense = TransactionType(name="expense", sign=-1)
        transfer = TransactionType(name="transfer", sign=0)
        s.add_all([income, expense, transfer])
        s.flush()
        checking = AccountType(name="checking")
        s.add(checking)
        s.flush()
        s.add(
            Account(
                nickname="chase",
                bank_name="Chase",
                account_type=checking,
                last_four="1234",
            )
        )
        s.add(Category(name="groceries", type=expense))
        s.add(Category(name="dining", type=expense))
        s.commit()

    yield TestSession


def _invoke_record(**kwargs: Any) -> str:
    """Call the underlying record_transaction function (bypasses @tool wrapper)."""
    return tools.record_transaction.func(**kwargs)


def test_resume_with_edits_overrides_fields(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resume payload with edit fields applies them to the written row."""
    # Pretend the user resumed with edits to description + is_test.
    resume_value = {
        "confirm": True,
        "description": "Whole Foods Test",
        "is_test": True,
    }
    monkeypatch.setattr(tools, "interrupt", lambda _payload: resume_value)

    result = _invoke_record(
        amount=10.0,
        type="expense",
        description="Whole Foods",
        date="2026-06-18",
        category="groceries",
        account="chase",
        is_test=False,
    )

    assert "recorded transaction" in result
    assert "Whole Foods Test" in result
    assert "[TEST]" in result

    # Verify what got written.
    with db() as s:
        from agent.db.models import Transaction

        rows = s.query(Transaction).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.description == "Whole Foods Test"
        assert row.is_test is True
        assert row.category.name == "groceries"
        assert row.account.nickname == "chase"
        from decimal import Decimal

        assert row.amount == Decimal("10")


def test_resume_with_edits_clears_account(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty string for account in the resume payload writes None."""
    monkeypatch.setattr(
        tools,
        "interrupt",
        lambda _payload: {"confirm": True, "account": "", "category": ""},
    )

    result = _invoke_record(
        amount=5.0,
        type="expense",
        description="Coffee",
        date="2026-06-18",
        category="groceries",
        account="chase",
    )
    assert "recorded transaction" in result

    with db() as s:
        from agent.db.models import Transaction

        row = s.query(Transaction).one()
        assert row.account is None
        assert row.category is None


def test_resume_with_edits_invalid_account_returns_error(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing the account to a nonexistent nickname returns an error."""
    monkeypatch.setattr(
        tools,
        "interrupt",
        lambda _payload: {"confirm": True, "account": "nope-bank"},
    )

    result = _invoke_record(
        amount=5.0,
        type="expense",
        description="Coffee",
        date="2026-06-18",
        category="groceries",
        account="chase",
    )
    assert "no account with nickname 'nope-bank'" in result


def test_resume_with_edits_invalid_amount_returns_error(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-decimal amount in the resume payload returns a clear error."""
    monkeypatch.setattr(
        tools, "interrupt", lambda _payload: {"confirm": True, "amount": "not-a-number"}
    )

    result = _invoke_record(
        amount=5.0,
        type="expense",
        description="Coffee",
        date="2026-06-18",
        category="groceries",
        account="chase",
    )
    assert "invalid amount" in result


def test_resume_with_plain_yes_writes_original(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing 'yes' path still writes the proposed transaction."""
    monkeypatch.setattr(tools, "interrupt", lambda _payload: "yes")

    result = _invoke_record(
        amount=12.5,
        type="expense",
        description="Coffee",
        date="2026-06-18",
        category="groceries",
        account="chase",
    )
    assert "recorded transaction" in result

    with db() as s:
        from agent.db.models import Transaction

        row = s.query(Transaction).one()
        assert row.description == "Coffee"
        assert row.is_test is False


def test_resume_declined_returns_no_write(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 'no' resume value declines without writing."""
    monkeypatch.setattr(tools, "interrupt", lambda _payload: "no")

    result = _invoke_record(
        amount=12.5,
        type="expense",
        description="Coffee",
        date="2026-06-18",
        category="groceries",
        account="chase",
    )
    assert "user declined" in result

    with db() as s:
        from agent.db.models import Transaction

        assert s.query(Transaction).count() == 0
