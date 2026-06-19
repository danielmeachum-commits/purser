"""add monthly_budget/target_amount to categories and create savings_goals

Revision ID: 0002_budgets_and_savings
Revises: 0001_initial
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_budgets_and_savings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(
            sa.Column("monthly_budget", sa.Numeric(12, 2), nullable=True)
        )
        batch.add_column(
            sa.Column("target_amount", sa.Numeric(12, 2), nullable=True)
        )

    op.create_table(
        "savings_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "allocated_amount",
            sa.Numeric(12, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("savings_goals")
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("target_amount")
        batch.drop_column("monthly_budget")
