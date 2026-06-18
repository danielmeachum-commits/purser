"""Categories — read + admin writes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent import queries
from agent.db import Category, Transaction, TransactionType, session_scope
from api.auth import Principal, require_admin, require_reader
from api.pubsub import broadcast
from api.schemas import CategoryCreate, CategoryUpdate

router = APIRouter(tags=["categories"])


def _serialize(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "type": c.type.name,
        "parent": c.parent.name if c.parent else None,
        "parent_id": c.parent_id,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/categories")
def list_categories(
    type: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    _: Principal = Depends(require_reader),
) -> list[dict]:
    return queries.list_categories(type=type, include_inactive=include_inactive)


@router.post("/categories", status_code=201)
def create_category(
    body: CategoryCreate, _: Principal = Depends(require_admin)
) -> dict:
    with session_scope() as s:
        tt = s.query(TransactionType).filter_by(name=body.type).first()
        if tt is None:
            raise HTTPException(
                status_code=400, detail=f"unknown transaction type {body.type!r}"
            )
        parent_cat = None
        if body.parent is not None:
            matches = s.query(Category).filter_by(
                name=body.parent, type_id=tt.id
            ).all()
            if not matches:
                raise HTTPException(
                    status_code=400,
                    detail=f"no {body.type} category named {body.parent!r}",
                )
            if len(matches) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"parent {body.parent!r} is ambiguous ({len(matches)} matches)",
                )
            parent_cat = matches[0]
        if s.query(Category).filter_by(
            name=body.name,
            parent_id=parent_cat.id if parent_cat else None,
            type_id=tt.id,
        ).first() is not None:
            raise HTTPException(
                status_code=409,
                detail="category already exists with that name+parent+type",
            )
        try:
            cat = Category(name=body.name, type=tt, parent=parent_cat)
            s.add(cat)
            s.flush()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        result = _serialize(cat)
    broadcast({"type": "category.new", "category": result})
    return result


@router.patch("/categories/{category_id}")
def update_category(
    category_id: int, body: CategoryUpdate, _: Principal = Depends(require_admin)
) -> dict:
    with session_scope() as s:
        cat = s.get(Category, category_id)
        if cat is None:
            raise HTTPException(status_code=404, detail="category not found")
        if body.name is not None:
            cat.name = body.name
        if body.parent is not None:
            if body.parent == "":
                cat.parent = None
            else:
                matches = s.query(Category).filter_by(
                    name=body.parent, type_id=cat.type_id
                ).all()
                if not matches:
                    raise HTTPException(
                        status_code=400,
                        detail=f"no category named {body.parent!r} with the same type",
                    )
                cat.parent = matches[0]
        if body.is_active is not None:
            cat.is_active = body.is_active
        s.flush()
        result = _serialize(cat)
    broadcast({"type": "category.updated", "category": result})
    return result


# Reference to avoid unused-import warnings in linters.
_ = Transaction
