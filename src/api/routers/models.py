"""GET /models — read-only chat model catalog from ``models.json``."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["models"])


def _models_config_path() -> Path:
    env = os.environ.get("MODELS_CONFIG_PATH")
    if env:
        return Path(env)
    # src/api/routers/models.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / "models.json"


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    path = _models_config_path()
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as e:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail=f"models.json not found at {path}"
        ) from e
    except json.JSONDecodeError as e:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail=f"models.json is not valid JSON: {e}"
        ) from e


@router.get("/models")
def get_models() -> dict[str, Any]:
    """Return the parsed contents of ``models.json``."""
    return _load_catalog()
