#!/usr/bin/env python3
"""Fetch /eink.png from the budget API and push it to the Inky Impression.

Config via env vars (also picked up from /etc/budget-eink/config.env by the
systemd unit):

    BUDGET_API_URL    base URL of the FastAPI service (e.g. http://server:8000)
    BUDGET_API_TOKEN  bgt_... read token

Exits non-zero on any failure; the systemd timer will fire again on schedule.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import urllib.error
import urllib.request

from PIL import Image

LOG = logging.getLogger("budget-eink")

DEFAULT_TIMEOUT = 30.0


def fetch_png(api_url: str, token: str, *, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """GET /eink.png with the bearer token; raise on non-200."""
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/eink.png",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "image/png",
            "User-Agent": "budget-eink/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"API returned HTTP {resp.status}")
        return resp.read()


def push_to_inky(png_bytes: bytes) -> None:
    """Decode the PNG and draw it to the Inky panel."""
    # Imported lazily so `--help` / config errors don't require the inky lib.
    from inky.auto import auto  # type: ignore[import-not-found]

    img = Image.open(io.BytesIO(png_bytes))
    display = auto()
    display.set_image(img)
    display.show()


def refresh(api_url: str, token: str) -> None:
    """Fetch the latest eink PNG and push it to the panel.

    Raises on any failure; callers decide whether to swallow or propagate.
    """
    png = fetch_png(api_url, token)
    LOG.info("fetched %d bytes; pushing to Inky", len(png))
    push_to_inky(png)
    LOG.info("display refreshed")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    api_url = os.environ.get("BUDGET_API_URL")
    token = os.environ.get("BUDGET_API_TOKEN")
    if not api_url or not token:
        LOG.error("BUDGET_API_URL and BUDGET_API_TOKEN must be set")
        return 2

    try:
        refresh(api_url, token)
    except urllib.error.HTTPError as e:
        LOG.error("fetch failed: HTTP %s — %s", e.code, e.reason)
        return 1
    except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
        LOG.error("fetch failed: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001
        LOG.exception("inky push failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
