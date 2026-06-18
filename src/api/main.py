"""Uvicorn entry point: `python -m api.main` or `budget-api`."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Start uvicorn serving the FastAPI app."""
    uvicorn.run(
        "api.app:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=os.environ.get("API_RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
