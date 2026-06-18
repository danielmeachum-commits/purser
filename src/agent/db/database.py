"""SQLite engine, session factory, and schema initialization."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agent.db.models import AccountType, Base, TransactionType

_DEFAULT_TRANSACTION_TYPES: tuple[tuple[str, int], ...] = (
    ("income", 1),
    ("expense", -1),
    ("transfer", 0),
)

_DEFAULT_ACCOUNT_TYPES: tuple[str, ...] = (
    "checking",
    "savings",
    "investment",
    "credit_card",
    "cash",
)

REPO_ROOT = Path(__file__).resolve().parents[3]
# BUDGET_DB_PATH overrides the default for containers / tests.
_DB_OVERRIDE = os.environ.get("BUDGET_DB_PATH")
DB_PATH = Path(_DB_OVERRIDE) if _DB_OVERRIDE else REPO_ROOT / "db" / "budget.sqlite"
DB_DIR = DB_PATH.parent
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create the data directory, schema, and seed lookup tables.

    Idempotent: safe to re-run. Seeded rows are inserted only when missing.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _seed_lookups()


def _seed_lookups() -> None:
    """Insert default transaction_types and account_types if absent."""
    with session_scope() as session:
        existing_tx_types = {t.name for t in session.query(TransactionType).all()}
        for name, sign in _DEFAULT_TRANSACTION_TYPES:
            if name not in existing_tx_types:
                session.add(TransactionType(name=name, sign=sign))

        existing_acct_types = {t.name for t in session.query(AccountType).all()}
        for name in _DEFAULT_ACCOUNT_TYPES:
            if name not in existing_acct_types:
                session.add(AccountType(name=name))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session, committing on success and rolling back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")  # noqa: T201
