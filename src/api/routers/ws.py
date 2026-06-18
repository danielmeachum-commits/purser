"""WebSocket endpoint: subscribers receive DB events (transaction.new, ...).

Authentication is performed at handshake from either the session cookie
or a `?token=...` query parameter (browsers can't set custom headers on
a WS upgrade, so Bearer headers aren't supported here).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from api.auth import decode_session_jwt, resolve_service_token
from api.config import get_settings
from api.pubsub import get_hub

log = logging.getLogger(__name__)
router = APIRouter()


def _authenticated(ws: WebSocket) -> bool:
    settings = get_settings()
    cookie = ws.cookies.get(settings.cookie_name)
    if cookie and decode_session_jwt(cookie, settings):
        return True
    token = ws.query_params.get("token")
    if token and resolve_service_token(token):
        return True
    return False


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if not _authenticated(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await ws.accept()
    hub = get_hub()
    queue = await hub.subscribe()
    try:
        await ws.send_json({"type": "hello"})
        # Reader task drains client → server; we don't expect messages,
        # but reading lets us detect disconnects promptly.
        async def _reader() -> None:
            try:
                while True:
                    await ws.receive_text()
            except WebSocketDisconnect:
                pass

        reader = asyncio.create_task(_reader())
        try:
            while True:
                event = await queue.get()
                await ws.send_json(event)
        finally:
            reader.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("websocket loop failed")
    finally:
        await hub.unsubscribe(queue)
