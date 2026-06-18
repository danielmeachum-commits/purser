"""Background task: watch the transactions table for new rows.

We don't (yet) route MCP/LangGraph writes through the API, so the API
can't broadcast them inline. This poller scans `transactions.created_at`
on a short interval and emits a `transaction.new` event per new row.

API write endpoints call `mark_broadcast(created_at)` after they emit
their own event, so the poller's cutoff jumps past API-originated writes
and we don't double-broadcast.

Replace with SQLite update hooks or move to API-only writes when the
extra latency becomes a problem.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from agent.db import session_scope
from agent.db.models import Transaction
from agent.queries import _serialize_tx
from api.config import get_settings
from api.pubsub import broadcast

log = logging.getLogger(__name__)

_cutoff: datetime | None = None


def mark_broadcast(created_at: datetime | None) -> None:
    """Advance the poller cutoff so it skips this row on its next pass."""
    global _cutoff
    if created_at is None:
        return
    if _cutoff is None or created_at > _cutoff:
        _cutoff = created_at


async def run_forever() -> None:
    """Poll for new transactions and broadcast each one."""
    global _cutoff
    settings = get_settings()
    _cutoff = _max_created_at()
    while True:
        try:
            await asyncio.sleep(settings.poll_interval_seconds)
            new_rows = _fetch_since(_cutoff)
            for row, created in new_rows:
                broadcast({"type": "transaction.new", "transaction": row})
                if _cutoff is None or created > _cutoff:
                    _cutoff = created
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("poller iteration failed")


def _max_created_at() -> datetime | None:
    with session_scope() as s:
        row = s.query(Transaction.created_at).order_by(
            Transaction.created_at.desc()
        ).first()
        return row[0] if row else None


def _fetch_since(cutoff: datetime | None) -> list[tuple[dict, datetime]]:
    with session_scope() as s:
        q = s.query(Transaction)
        if cutoff is not None:
            q = q.filter(Transaction.created_at > cutoff)
        q = q.order_by(Transaction.created_at.asc()).limit(50)
        return [(_serialize_tx(tx), tx.created_at) for tx in q.all()]
