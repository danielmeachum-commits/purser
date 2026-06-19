"""SQLAlchemy ORM models for financial transactions."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class TransactionType(Base):
    """A kind of money movement: income, expense, or transfer.

    `sign` carries the direction (+1 income, -1 expense, 0 transfer), so
    aggregations can use `amount * sign` instead of CASE WHEN.
    """

    __tablename__ = "transaction_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(16), unique=True)
    sign: Mapped[int] = mapped_column(SmallInteger)

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"TransactionType(id={self.id}, name={self.name!r}, sign={self.sign})"


class AccountType(Base):
    """A kind of bank account: checking, savings, investment, etc."""

    __tablename__ = "account_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)

    def __repr__(self) -> str:
        """Return a debug representation."""
        return f"AccountType(id={self.id}, name={self.name!r})"


class Account(Base):
    """A real-world financial account.

    Only the last 4 digits of the account number are stored. `nickname`
    is the natural lookup key for the agent (e.g. "amex", "chase checking").
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), unique=True)
    bank_name: Mapped[str] = mapped_column(String(64))
    account_type_id: Mapped[int] = mapped_column(ForeignKey("account_types.id"))
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account_type: Mapped[AccountType] = relationship()

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"Account(id={self.id}, nickname={self.nickname!r}, "
            f"bank_name={self.bank_name!r}, last_four={self.last_four!r})"
        )


class Category(Base):
    """A spending or income category, optionally nested under a parent.

    Each category is bound to exactly one `TransactionType`; a subcategory
    must share its parent's type (enforced by validator).
    """

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", "parent_id", "type_id", name="uq_category_sibling"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    type_id: Mapped[int] = mapped_column(ForeignKey("transaction_types.id"))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    monthly_budget: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    target_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    type: Mapped[TransactionType] = relationship()
    parent: Mapped[Category | None] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list[Category]] = relationship(back_populates="parent")

    @validates("parent")
    def _check_parent_type(self, _key: str, parent: Category | None) -> Category | None:
        # Compare the related TransactionType objects: the FK columns aren't
        # populated until flush, so they're unreliable here.
        if parent is not None and self.type is not None and parent.type is not None:
            if self.type.name != parent.type.name:
                raise ValueError(
                    f"subcategory type ({self.type.name!r}) must match parent type "
                    f"({parent.type.name!r})"
                )
        return parent

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"Category(id={self.id}, name={self.name!r}, "
            f"type_id={self.type_id}, parent_id={self.parent_id})"
        )


class Transaction(Base):
    """A single financial transaction.

    `amount` is stored as a positive decimal; direction comes from
    `type.sign`. Category and account are optional FK references.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    type_id: Mapped[int] = mapped_column(ForeignKey("transaction_types.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(String(255))
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    type: Mapped[TransactionType] = relationship()
    category: Mapped[Category | None] = relationship()
    account: Mapped[Account | None] = relationship()

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"Transaction(id={self.id}, date={self.date}, amount={self.amount}, "
            f"type_id={self.type_id}, description={self.description!r}, "
            f"category_id={self.category_id}, account_id={self.account_id}, "
            f"is_test={self.is_test})"
        )


class SavingsGoal(Base):
    """A named savings target with a manually-tracked allocated balance.

    `allocated_amount` is a freeform number the operator updates as they
    move money toward the goal; it isn't auto-derived from transactions.
    """

    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0"
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account | None] = relationship()

    def __repr__(self) -> str:
        """Return a debug representation."""
        return (
            f"SavingsGoal(id={self.id}, name={self.name!r}, "
            f"target={self.target_amount}, allocated={self.allocated_amount})"
        )
