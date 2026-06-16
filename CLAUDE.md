# budget-graph

A LangGraph agent for recording and querying personal financial transactions
through a chat interface (Claude Code, LangGraph Studio, etc.). Transactions
are persisted to a local SQLite database managed by SQLAlchemy 2.0.

## Layout

- `src/agent/` — LangGraph agent package (entry point: `agent.graph:graph`)
- `src/agent/db/` — SQLAlchemy models, engine, and session management
- `db/budget.sqlite` — SQLite database file (gitignored)
- `langgraph.json` — LangGraph CLI / Studio configuration
- `.env` — local secrets (LangSmith key, etc.)

## Database

- ORM: SQLAlchemy 2.0 (`DeclarativeBase` + `Mapped[...]` style)
- Engine URL: `sqlite:///<repo-root>/db/budget.sqlite`
- No migration tool (Alembic) yet — schema is created with
  `Base.metadata.create_all()`. If the schema changes, either delete
  `db/budget.sqlite` and re-run `init_db()`, or add Alembic.

### Schema

Five tables: three lookups (`transaction_types`, `account_types`), two
"real" tables (`accounts`, `categories`), and the `transactions` fact table.

#### `transaction_types`
| column | type             | notes                                       |
|--------|------------------|---------------------------------------------|
| `id`   | INTEGER PK       |                                             |
| `name` | VARCHAR(16) UNIQUE | `income`, `expense`, `transfer`           |
| `sign` | SMALLINT         | `+1` income, `-1` expense, `0` transfer     |

Seeded by `init_db()` with the three rows above.

#### `account_types`
| column | type               | notes                                                    |
|--------|--------------------|----------------------------------------------------------|
| `id`   | INTEGER PK         |                                                          |
| `name` | VARCHAR(32) UNIQUE | `checking`, `savings`, `investment`, `credit_card`, `cash` |

Seeded by `init_db()`.

#### `accounts` — your real bank accounts
| column            | type                 | notes                                                |
|-------------------|----------------------|------------------------------------------------------|
| `id`              | INTEGER PK           |                                                      |
| `nickname`        | VARCHAR(64) UNIQUE   | natural lookup key (`"amex"`, `"chase checking"`)    |
| `bank_name`       | VARCHAR(64)          | `"Chase"`, `"Amex"`; use `"Cash"` for cash accounts  |
| `account_type_id` | INTEGER FK           | → `account_types.id`                                 |
| `last_four`       | VARCHAR(4)           | nullable; string preserves leading zeros             |
| `is_active`       | BOOLEAN              | default TRUE; flip to FALSE to retire an account     |
| `created_at`      | DATETIME             | server default `CURRENT_TIMESTAMP`                   |

#### `categories` — hierarchical, tied to a transaction type
| column       | type        | notes                                                       |
|--------------|-------------|-------------------------------------------------------------|
| `id`         | INTEGER PK  |                                                             |
| `name`       | VARCHAR(64) |                                                             |
| `type_id`    | INTEGER FK  | → `transaction_types.id`; income-only or expense-only       |
| `parent_id`  | INTEGER FK  | → `categories.id`; nullable (top-level when NULL)           |
| `is_active`  | BOOLEAN     | default TRUE                                                |
| `created_at` | DATETIME    | server default `CURRENT_TIMESTAMP`                          |

- Unique constraint `(name, parent_id, type_id)` — siblings must differ.
- A subcategory must share its parent's `type_id` (enforced by an ORM
  validator on `Category.parent`, not by SQL).
- Not seeded — add categories as you need them.

#### `transactions`
| column        | type           | notes                                          |
|---------------|----------------|------------------------------------------------|
| `id`          | INTEGER PK     |                                                |
| `date`        | DATE           | indexed                                        |
| `amount`      | NUMERIC(12, 2) | always positive — direction comes from `type.sign` |
| `type_id`     | INTEGER FK     | → `transaction_types.id`, indexed              |
| `category_id` | INTEGER FK     | → `categories.id`, nullable, indexed           |
| `account_id`  | INTEGER FK     | → `accounts.id`, nullable, indexed             |
| `description` | VARCHAR(255)   | free-text payee / memo                         |
| `created_at`  | DATETIME       | server default `CURRENT_TIMESTAMP`             |

Sign convention: `amount` is positive. For a signed total, join to
`transaction_types` and multiply by `sign`.

### Initialize / reset the DB

```bash
uv run python -m agent.db.database
```

Idempotent — creates `db/budget.sqlite`, all five tables, and seeds the
default `transaction_types` and `account_types` rows if missing. To reset
the schema after a model change, delete `db/budget.sqlite` first.

### Public API (`from agent.db import ...`)

- `Base` — declarative base
- `TransactionType`, `AccountType`, `Account`, `Category`, `Transaction` — ORM models
- `engine`, `SessionLocal` — SQLAlchemy engine and session factory
- `init_db()` — create directory + tables + seed lookups
- `session_scope()` — context manager that commits on success, rolls back
  on error, and always closes
- `DATABASE_URL`, `DB_PATH` — for tools/tests that need them

### Usage pattern

```python
from datetime import date
from decimal import Decimal
from agent.db import (
    Account, AccountType, Category, Transaction, TransactionType,
    session_scope,
)

# Add an account and a category once
with session_scope() as s:
    checking = s.query(AccountType).filter_by(name="checking").one()
    expense = s.query(TransactionType).filter_by(name="expense").one()
    s.add(Account(
        nickname="chase checking", bank_name="Chase",
        account_type=checking, last_four="1234",
    ))
    s.add(Category(name="food", type=expense))

# Record a transaction by looking up FK rows
with session_scope() as s:
    expense = s.query(TransactionType).filter_by(name="expense").one()
    food = s.query(Category).filter_by(name="food").one()
    acct = s.query(Account).filter_by(nickname="chase checking").one()
    s.add(Transaction(
        date=date(2026, 6, 14), amount=Decimal("12.50"),
        type=expense, description="Coffee",
        category=food, account=acct,
    ))

# Query by relationship
with session_scope() as s:
    rows = (
        s.query(Transaction)
        .join(Transaction.category)
        .filter(Category.name == "food")
        .all()
    )
```

Always use `Decimal` (not `float`) for `amount` — `Numeric` round-trips to
`Decimal` and float arithmetic loses cents.

## Running the agent

```bash
uv sync                # install deps into .venv
langgraph dev          # serve the graph locally for LangGraph Studio
```

Studio config in `langgraph.json` exposes the `agent` graph defined at
`src/agent/graph.py`.

## Conventions

- Python 3.10+ (project pinned via `requires-python`).
- Package layout is `src/`-based. New top-level packages must be registered
  in `pyproject.toml` under `[tool.setuptools]` — there is **no** top-level
  `db` package; database code lives at `agent.db` because a root-level
  `db/` data directory would shadow it as a namespace package.
- Lint: `ruff` (Google docstring convention, see `[tool.ruff]`).
- Tests: `pytest`, split into `tests/unit_tests/` and `tests/integration_tests/`.
