"""In-process pub/sub for broadcasting DB events to WebSocket subscribers.

Two event sources:

- API write endpoints (phase 5) call `broadcast({"type": "...", ...})`
  directly after a successful commit.
- A background poller (`poller.run_forever`) watches `MAX(created_at)` on
  the `transactions` table and broadcasts new rows so dashboards still
  update when transactions are written by LangGraph or MCP.

Both call into the same `Hub`, so subscribers see a single feed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


class Hub:
    """Fan-out pub/sub. One queue per subscriber, lossy under backpressure."""

    def __init__(self, queue_size: int = 100) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        """Best-effort fan-out. Drop oldest item on a full queue."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:  # noqa: BLE001
                    log.warning("failed to drain full subscriber queue")


_hub: Hub | None = None


def get_hub() -> Hub:
    """Return the process-wide singleton hub (lazy-init)."""
    global _hub
    if _hub is None:
        _hub = Hub()
    return _hub


def broadcast(event: dict[str, Any]) -> None:
    """Publish an event to all subscribers."""
    get_hub().publish(event)
