"""SQLite engine, session factory, and schema initialization."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from agent.db.models import AccountType, TransactionType

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


_ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def init_db() -> None:
    """Create the data directory, run Alembic migrations, seed lookups.

    Idempotent: safe to re-run. Pre-Alembic databases (created with the
    old `Base.metadata.create_all()` path) are stamped at the baseline
    revision the first time `init_db()` runs so subsequent upgrades apply
    cleanly without trying to recreate existing tables.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    _run_migrations()
    _seed_lookups()


def _run_migrations() -> None:
    # Imported lazily so the unit tests that touch models don't pay the
    # alembic import cost, and so a missing config doesn't break imports.
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    insp = inspect(engine)
    has_alembic = insp.has_table("alembic_version")
    has_transactions = insp.has_table("transactions")
    if has_transactions and not has_alembic:
        # Pre-Alembic DB: claim it matches the baseline revision.
        command.stamp(cfg, "0001_initial")
    command.upgrade(cfg, "head")


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
