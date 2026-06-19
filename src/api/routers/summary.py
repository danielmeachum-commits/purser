"""Signed-total summaries (passthrough to agent.queries.summarize_transactions)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent import queries
from api.auth import Principal, require_reader

router = APIRouter(tags=["summary"])


@router.get("/summary")
def summary(
    date_range: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    period: str | None = Query(default=None),
    group_by: list[str] | None = Query(default=None),
    include_transactions: bool = Query(default=False),
    extended_metrics: bool = Query(default=False),
    test_mode: str = Query(default="exclude"),
    _: Principal = Depends(require_reader),
) -> dict:
    # FastAPI gives an empty list when group_by is absent — collapse to None
    # so the default "category" kicks in inside queries.summarize_transactions.
    if group_by is None or group_by == []:
        gb: str | list[str] | None = "category"
    elif len(group_by) == 1 and group_by[0].lower() in ("none", ""):
        gb = None
    elif len(group_by) == 1 and "," in group_by[0]:
        gb = group_by[0]
    else:
        gb = group_by
    result = queries.summarize_transactions(
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
        period=period,
        group_by=gb,
        include_transactions=include_transactions,
        extended_metrics=extended_metrics,
        test_mode=test_mode,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/summary/categories")
def category_breakdown(
    date_range: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    test_mode: str = Query(default="exclude"),
    _: Principal = Depends(require_reader),
) -> dict:
    """Per-category direct totals with parent_id + budget fields.

    Dedicated to the dashboard's nested-by-parent view: keys by category
    id (not name) so children can be safely re-attached to their parent.
    Rollups are computed client-side.
    """
    result = queries.category_breakdown(
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
        test_mode=test_mode,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
