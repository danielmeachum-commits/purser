"""Pre-rendered eink dashboard image + manual-refresh signal for the Pi."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.auth import Principal, require_admin, require_reader
from api.eink import render_eink_png
from api.pubsub import broadcast

router = APIRouter(tags=["eink"])


@router.get("/eink.png")
def eink_png(_: Principal = Depends(require_reader)) -> Response:
    """Return the 800x480 palettized PNG for the Inky panel.

    The Pi blits this straight to the display — palette quantization
    happens here, server-side.
    """
    return Response(
        content=render_eink_png(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/eink/refresh", status_code=202)
def request_refresh(_: Principal = Depends(require_admin)) -> dict[str, str]:
    """Broadcast an `eink.refresh` event so a listening Pi pulls + redraws.

    No-op if no Pi is connected; the hourly systemd timer is the fallback.
    """
    broadcast({"type": "eink.refresh"})
    return {"status": "requested"}
