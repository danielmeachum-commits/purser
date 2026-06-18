"""FastAPI app for the budget-graph dashboard + admin."""

# Importing models here registers them on agent.db.Base so init_db() creates them.
from api import models  # noqa: F401
from api.app import create_app

__all__ = ["create_app"]
