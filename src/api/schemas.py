"""Pydantic request/response schemas shared across routers."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- auth ------------------------------------------------------------------


class LoginRequest(BaseModel):
    password: str


class WhoAmI(BaseModel):
    authenticated: bool
    scope: Literal["admin", "read"] | None = None
    source: Literal["session", "token"] | None = None


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scope: Literal["admin", "read"] = "read"


class TokenInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scope: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class TokenCreated(TokenInfo):
    token: str  # the only time the plaintext is returned


# --- domain ----------------------------------------------------------------


class AccountType(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class AccountTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class TransactionType(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sign: int


class Account(BaseModel):
    id: int
    nickname: str
    bank_name: str
    account_type: str
    last_four: str | None = None
    is_active: bool
    created_at: datetime


class AccountCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)
    bank_name: str = Field(min_length=1, max_length=64)
    account_type: str
    last_four: str | None = Field(default=None, max_length=4)


class AccountUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    bank_name: str | None = Field(default=None, min_length=1, max_length=64)
    account_type: str | None = None
    last_four: str | None = Field(default=None, max_length=4)
    is_active: bool | None = None


class Category(BaseModel):
    id: int
    name: str
    type: str
    parent: str | None = None
    parent_id: int | None = None
    is_active: bool
    monthly_budget: Decimal | None = None
    target_amount: Decimal | None = None
    created_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: Literal["income", "expense", "transfer"]
    parent: str | None = None
    monthly_budget: Decimal | None = None
    target_amount: Decimal | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    parent: str | None = None
    is_active: bool | None = None
    # Use a sentinel string "" for "clear this field" (matches parent's
    # existing convention). Decimal | None means "not set"; explicit null
    # in JSON also means clear.
    monthly_budget: Decimal | None = None
    target_amount: Decimal | None = None
    clear_monthly_budget: bool = False
    clear_target_amount: bool = False


# --- savings goals ---------------------------------------------------------


class SavingsGoal(BaseModel):
    """Response shape for a savings goal."""

    id: int
    name: str
    target_amount: Decimal
    allocated_amount: Decimal
    account: str | None = None
    account_id: int | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime


class SavingsGoalCreate(BaseModel):
    """Body for POST /savings-goals."""

    name: str = Field(min_length=1, max_length=64)
    target_amount: Decimal = Field(gt=0)
    allocated_amount: Decimal = Field(default=Decimal("0"), ge=0)
    account: str | None = None
    notes: str | None = Field(default=None, max_length=255)


class SavingsGoalUpdate(BaseModel):
    """Body for PATCH /savings-goals/{id}; "" on `account` clears it."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    target_amount: Decimal | None = Field(default=None, gt=0)
    allocated_amount: Decimal | None = Field(default=None, ge=0)
    account: str | None = None
    notes: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class Transaction(BaseModel):
    id: int
    date: date_type
    amount: Decimal
    type: str
    category: str | None = None
    account: str | None = None
    description: str
    is_test: bool
    created_at: datetime


class TransactionUpdate(BaseModel):
    date: date_type | None = None
    amount: Decimal | None = None
    type: Literal["income", "expense", "transfer"] | None = None
    category: str | None = None
    account: str | None = None
    description: str | None = Field(default=None, max_length=255)
    is_test: bool | None = None
