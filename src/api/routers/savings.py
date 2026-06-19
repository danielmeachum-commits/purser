"""Savings goals — manually-tracked targets and allocations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from agent import queries
from agent.db import Account, SavingsGoal, session_scope
from api.auth import Principal, require_admin, require_reader
from api.pubsub import broadcast
from api.schemas import SavingsGoalCreate, SavingsGoalUpdate

router = APIRouter(tags=["savings_goals"])


def _serialize(g: SavingsGoal) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": str(g.target_amount),
        "allocated_amount": str(g.allocated_amount),
        "account": g.account.nickname if g.account else None,
        "account_id": g.account_id,
        "notes": g.notes,
        "is_active": g.is_active,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _resolve_account(s, nickname: str) -> Account:
    acct = s.query(Account).filter_by(nickname=nickname).first()
    if acct is None:
        raise HTTPException(
            status_code=400, detail=f"no account with nickname {nickname!r}"
        )
    return acct


@router.get("/savings-goals")
def list_savings_goals(
    include_inactive: bool = Query(default=False),
    _: Principal = Depends(require_reader),
) -> list[dict]:
    """List savings goals ordered by name."""
    return queries.list_savings_goals(include_inactive=include_inactive)


@router.post("/savings-goals", status_code=201)
def create_savings_goal(
    body: SavingsGoalCreate, _: Principal = Depends(require_admin)
) -> dict:
    """Create a savings goal."""
    with session_scope() as s:
        if s.query(SavingsGoal).filter_by(name=body.name).first() is not None:
            raise HTTPException(
                status_code=409, detail=f"savings goal {body.name!r} already exists"
            )
        account = _resolve_account(s, body.account) if body.account else None
        goal = SavingsGoal(
            name=body.name,
            target_amount=body.target_amount,
            allocated_amount=body.allocated_amount,
            account=account,
            notes=body.notes,
        )
        s.add(goal)
        s.flush()
        result = _serialize(goal)
    broadcast({"type": "savings_goal.new", "savings_goal": result})
    return result


@router.patch("/savings-goals/{goal_id}")
def update_savings_goal(
    goal_id: int, body: SavingsGoalUpdate, _: Principal = Depends(require_admin)
) -> dict:
    """Update a savings goal."""
    with session_scope() as s:
        goal = s.get(SavingsGoal, goal_id)
        if goal is None:
            raise HTTPException(status_code=404, detail="savings goal not found")
        if body.name is not None and body.name != goal.name:
            if s.query(SavingsGoal).filter_by(name=body.name).first() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"savings goal {body.name!r} already exists",
                )
            goal.name = body.name
        if body.target_amount is not None:
            goal.target_amount = body.target_amount
        if body.allocated_amount is not None:
            goal.allocated_amount = body.allocated_amount
        if body.account is not None:
            goal.account = None if body.account == "" else _resolve_account(s, body.account)
        if body.notes is not None:
            goal.notes = body.notes or None
        if body.is_active is not None:
            goal.is_active = body.is_active
        s.flush()
        result = _serialize(goal)
    broadcast({"type": "savings_goal.updated", "savings_goal": result})
    return result


@router.delete("/savings-goals/{goal_id}", status_code=204)
def delete_savings_goal(
    goal_id: int, _: Principal = Depends(require_admin)
) -> Response:
    """Delete a savings goal."""
    with session_scope() as s:
        goal = s.get(SavingsGoal, goal_id)
        if goal is None:
            raise HTTPException(status_code=404, detail="savings goal not found")
        s.delete(goal)
    broadcast({"type": "savings_goal.deleted", "id": goal_id})
    return Response(status_code=204)
