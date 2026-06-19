"""Alembic env: reuse the project's engine + metadata."""

from __future__ import annotations

from alembic import context

# Import the project's engine + metadata. agent.db.models registers all
# ORM tables; api.models registers AuthToken against the same Base.
from agent.db import Base, engine
import api.models  # noqa: F401  (side-effect: registers AuthToken)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a DBAPI connection."""
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the project's engine."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
