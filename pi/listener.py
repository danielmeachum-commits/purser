#!/usr/bin/env python3
"""Subscribe to the budget API's WebSocket and refresh the Inky on signal.

Refreshes when the API broadcasts an `eink.refresh` event (sent by
POST /eink/refresh from the dashboard) OR any data-change event
(`transaction.*`, `account.*`, `category.*`, `savings_goal.*`,
`account_type.*`). A cooldown prevents the panel from being asked to
redraw faster than it physically can.

Reconnects with exponential backoff on disconnect. The hourly systemd
timer (`budget-eink.timer`) stays as a safety net for when this daemon
isn't reachable.

Config via env vars (same as client.py):

    BUDGET_API_URL    base URL of the FastAPI service
    BUDGET_API_TOKEN  bgt_... read token
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from urllib.parse import urlsplit

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from client import refresh

LOG = logging.getLogger("budget-eink-listener")

REFRESH_COOLDOWN_SEC = 60.0
DEBOUNCE_SEC = 5.0
INITIAL_BACKOFF = 2.0
MAX_BACKOFF = 60.0

TRIGGER_PREFIXES: tuple[str, ...] = (
    "eink.refresh",
    "transaction.",
    "account.",
    "category.",
    "savings_goal.",
    "account_type.",
)


def _ws_url(api_url: str, token: str) -> str:
    """Build wss://host/ws?token=... from the http(s) API URL.

    Note: the websocket endpoint lives at /ws on the FastAPI service
    (nginx forwards it without the /api prefix), so we strip any path
    suffix the API URL might carry.
    """
    parts = urlsplit(api_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return f"{scheme}://{parts.netloc}/ws?token={token}"


async def _refresh_in_executor(api_url: str, token: str) -> None:
    """Run the blocking refresh on a thread so the event loop stays alive."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, refresh, api_url, token)


async def refresh_worker(
    trigger: asyncio.Event, api_url: str, token: str
) -> None:
    """Run a refresh whenever `trigger` is set, respecting cooldown.

    Debounces bursts of events: after the trigger fires, waits DEBOUNCE_SEC
    so multiple near-simultaneous changes coalesce into one refresh.
    """
    last_refresh = 0.0
    while True:
        await trigger.wait()
        await asyncio.sleep(DEBOUNCE_SEC)
        trigger.clear()

        wait_for = (last_refresh + REFRESH_COOLDOWN_SEC) - time.monotonic()
        if wait_for > 0:
            LOG.info("cooldown — sleeping %.1fs", wait_for)
            await asyncio.sleep(wait_for)

        try:
            await _refresh_in_executor(api_url, token)
            last_refresh = time.monotonic()
        except Exception as e:  # noqa: BLE001
            LOG.exception("refresh failed: %s", e)


async def listen(api_url: str, token: str, trigger: asyncio.Event) -> None:
    """Maintain a websocket subscription; set `trigger` on relevant events.

    Reconnects forever with exponential backoff. Never raises.
    """
    backoff = INITIAL_BACKOFF
    ws_url = _ws_url(api_url, token)
    log_url = ws_url.split("?", 1)[0]
    while True:
        try:
            LOG.info("connecting to %s", log_url)
            async with websockets.connect(ws_url, open_timeout=10) as ws:
                LOG.info("websocket connected")
                backoff = INITIAL_BACKOFF
                async for message in ws:
                    if not _should_trigger(message):
                        continue
                    LOG.info("trigger event: %s", _summarize(message))
                    trigger.set()
        except (ConnectionClosed, InvalidStatusCode, OSError) as e:
            LOG.warning("websocket disconnected (%s); retrying in %.1fs", e, backoff)
        except Exception as e:  # noqa: BLE001
            LOG.exception("websocket loop error: %s; retrying in %.1fs", e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF)


def _should_trigger(raw_message: str | bytes) -> bool:
    import json

    try:
        msg = json.loads(raw_message)
    except (ValueError, TypeError):
        return False
    if not isinstance(msg, dict):
        return False
    event_type = msg.get("type", "")
    if not isinstance(event_type, str):
        return False
    return any(event_type.startswith(p) for p in TRIGGER_PREFIXES)


def _summarize(raw_message: str | bytes) -> str:
    import json

    try:
        msg = json.loads(raw_message)
        return str(msg.get("type", "?"))
    except (ValueError, TypeError):
        return "?"


async def amain() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    api_url = os.environ.get("BUDGET_API_URL")
    token = os.environ.get("BUDGET_API_TOKEN")
    if not api_url or not token:
        LOG.error("BUDGET_API_URL and BUDGET_API_TOKEN must be set")
        return 2

    trigger = asyncio.Event()
    worker = asyncio.create_task(refresh_worker(trigger, api_url, token))
    listener = asyncio.create_task(listen(api_url, token, trigger))
    try:
        await asyncio.gather(worker, listener)
    finally:
        worker.cancel()
        listener.cancel()
    return 0


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
