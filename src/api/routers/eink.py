"""Pre-rendered eink dashboard image for the Pi client."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.auth import Principal, require_reader
from api.eink import render_eink_png

router = APIRouter(tags=["eink"])


@router.get("/eink.png")
def eink_png(_: Principal = Depends(require_reader)) -> Response:
    """Return the 800x480 7-color palettized PNG for the Inky panel.

    The Pi just blits this straight to the display — Floyd-Steinberg
    dithering and palette quantization happen here, server-side.
    """
    return Response(
        content=render_eink_png(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
