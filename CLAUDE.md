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
| `is_test`     | BOOLEAN        | default FALSE; flag throwaway/dev rows so they're excluded from list/summary by default |
| `created_at`  | DATETIME       | server default `CURRENT_TIMESTAMP`             |

Sign convention: `amount` is positive. For a signed total, join to
`transaction_types` and multiply by `sign`.

`list_transactions` and `summarize_transactions` both take an
`include_test` flag (default `False`) — set it to `True` to see test rows.

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
uv sync           # install deps into .venv
langgraph dev     # serve the graph at http://localhost:2024 (Studio + HTTP)
```

Studio config in `langgraph.json` exposes the `agent` graph defined at
`src/agent/graph.py`.

### NixOS: dev shell via `shell.nix` + direnv

`langgraph dev` imports `grpc`, whose cython extension links against
`libstdc++.so.6`. On NixOS that lib lives in `/nix/store` and isn't on
the default loader path, so the import fails with `ImportError:
libstdc++.so.6: cannot open shared object file`.

The repo's `shell.nix` exports `LD_LIBRARY_PATH` from nix-ld's lib set
(with `stdenv.cc.cc.lib` as a fallback). With direnv installed, run:

```bash
direnv allow      # one-time, picks up .envrc + shell.nix
```

After that, `cd`ing into the repo activates the env automatically — plain
`langgraph dev` (and any other command needing libstdc++) just works.

If you'd rather not use direnv:

- `nix-shell` drops you into the same env interactively
- `make dev` inlines the `NIX_LD_LIBRARY_PATH` fix and works either way

## Agent workflow

`src/agent/graph.py` builds a ReAct agent (`langgraph.prebuilt.create_react_agent`)
over the tools in `src/agent/tools.py`:

| Tool                     | Purpose                                           |
|--------------------------|---------------------------------------------------|
| `record_transaction`     | Insert a new transaction; interrupts for user confirmation before writing |
| `list_transactions`      | List recent rows; filter by date/category/account |
| `summarize_transactions` | Signed totals over a date range, optionally grouped |
| `list_categories`        | Read existing categories (used to auto-suggest a category before recording) |
| `add_account`            | Create a new account row                          |
| `add_category`           | Create a new category (optionally nested)         |

`record_transaction` does NOT silently create unknown accounts or
categories — it errors and asks the LLM to call `add_*` first.

### Category auto-suggest + write confirmation

The system prompt drives this flow when the user wants to log a transaction:

1. LLM calls `list_categories` (filtered to the transaction's type) and
   picks the best match by name/meaning.
2. If nothing fits, the LLM proposes a new category in chat, mentioning
   that it can be either a top-level category OR a subcategory of an
   existing related parent (e.g. `groceries` under `food`). On user
   agreement it calls `add_category`.
3. The LLM then calls `record_transaction`. **The tool itself calls
   `langgraph.types.interrupt()`** with a preview payload before any
   write — the graph pauses and the caller sees the interrupt. The
   user resumes the run with `yes`/`no`; on anything other than
   affirmative the tool returns `transaction not recorded — user
   declined` and no row is inserted.

Affirmative parsing in `_is_affirmative` (`src/agent/tools.py`) accepts
`yes`, `y`, `confirm`, `ok`, `okay`, `sure`, `go`, `do it`, `true`, or a
dict containing one of those under `confirm`/`approved`/`answer`/`response`.
Everything else counts as a decline.

Because `interrupt()` requires a checkpointer and the ability to resume,
calls that may hit `record_transaction` MUST go through a thread (see
the curl example below). Stateless `/runs/wait` calls cannot be resumed.

### LLM backend

The agent uses an OpenAI-compatible local LLM. Defaults:

- `LOCAL_LLM_BASE_URL` = `http://localhost:9292/v1` (llama-swap)
- `LOCAL_LLM_MODEL` = `gpt-oss-20b`
- `LOCAL_LLM_API_KEY` = `not-needed`

Override any of these via `.env` to point at a different endpoint or model.
The model must support OpenAI-style tool calls.

### Invoking from Claude Code

With `langgraph dev` running, use curl from the Claude Code shell.
Read-only operations (`list_transactions`, `summarize_transactions`,
`list_categories`) work as a single stateless call:

```bash
curl -sS http://localhost:2024/runs/wait \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "agent",
    "input": {"messages": [{"role": "user", "content": "Show my last 5 transactions"}]}
  }' | jq '.messages[-1].content'
```

Anything that hits `record_transaction` will pause on an interrupt and
needs a thread so the run can be resumed:

```bash
# 1. Create a thread
TID=$(curl -sS -XPOST http://localhost:2024/threads \
  -H 'Content-Type: application/json' -d '{}' | jq -r .thread_id)

# 2. First turn — returns with the interrupt payload in `__interrupt__`
curl -sS http://localhost:2024/threads/$TID/runs/wait \
  -H 'Content-Type: application/json' \
  -d '{
    "assistant_id": "agent",
    "input": {"messages": [{"role": "user",
      "content": "I spent $12.50 on coffee today at Blue Bottle"}]}
  }' | jq

# 3. Resume with yes/no — the tool either writes the row or cancels
curl -sS http://localhost:2024/threads/$TID/runs/wait \
  -H 'Content-Type: application/json' \
  -d '{"assistant_id":"agent","command":{"resume":"yes"}}' \
  | jq '.messages[-1].content'
```

Reuse the same `thread_id` for additional turns. The LangGraph dev API
docs at `http://localhost:2024/docs` cover the full surface.

## MCP server

`src/agent/mcp_server.py` exposes the same DB operations as MCP tools so
local clients (Claude Code, Claude Desktop, etc.) can use them directly
without going through `langgraph dev`. The server uses stdio transport
and is launched via the `budget-mcp` console script.

Tools exposed: `list_categories`, `list_accounts`, `list_transactions`,
`summarize_transactions`, `record_transaction`, `add_account`,
`add_category`.

### Confirmation model

The MCP runtime has no `interrupt()` equivalent. Instead `record_transaction`
uses a two-step confirm flag:

- Call with `confirm=False` (default) → tool validates and returns
  `{"status": "needs_confirmation", "transaction": {...}, "next": ...}`
  without writing. The MCP client must show this preview to the user.
- Call again with `confirm=True` after the user explicitly approves →
  tool writes and returns `{"status": "recorded", "id": ..., ...}`.

This relies on the MCP client (e.g. Claude Code) to act as the
human-in-the-loop layer, which it already does conversationally. The
LangGraph-side `record_transaction` still uses `interrupt()` — they're
independent code paths sharing the SQLAlchemy models.

### Wiring into Claude Code

The repo ships a project-scoped `.mcp.json` that points Claude Code at
`uv run budget-mcp`. After a fresh clone:

```bash
uv sync                       # picks up the `mcp` dep + budget-mcp script
```

Then restart Claude Code in the project directory. The first time it
sees `.mcp.json` it will ask you to approve the server. Once approved,
`/mcp` lists the connected server and its tools.

### Manually

```bash
uv run budget-mcp             # starts the server on stdio (for debugging)
```

- Python 3.10+ (project pinned via `requires-python`).
- Package layout is `src/`-based. New top-level packages must be registered
  in `pyproject.toml` under `[tool.setuptools]` — there is **no** top-level
  `db` package; database code lives at `agent.db` because a root-level
  `db/` data directory would shadow it as a namespace package.
- Lint: `ruff` (Google docstring convention, see `[tool.ruff]`).
- Tests: `pytest`, split into `tests/unit_tests/` and `tests/integration_tests/`.
