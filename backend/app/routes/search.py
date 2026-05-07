from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_scope
from app.database import get_db
from app.models import Company, Contact, Deal, Task, User, UserRole
from app.schemas import CompanyRead, ContactRead, DealRead, SearchResults, TaskRead

router = APIRouter(prefix="/api/search", tags=["search"])


def _apply_contact_ownership(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Contact.owner_id == user.id)
    return query


def _apply_company_ownership(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Company.owner_id == user.id)
    return query


def _apply_deal_ownership(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Deal.owner_id == user.id)
    return query


def _apply_task_ownership(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Task.assigned_to == user.id)
    return query


@router.get("", response_model=dict)
async def global_search(
    q: str = Query("", min_length=1),
    type: str | None = Query(None, pattern="^(contact|company|deal|task)$"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("search:read")),
):
    like = f"%{q}%"
    out: dict = {"contacts": [], "companies": [], "deals": [], "tasks": [],
                 "totals": {"contacts": 0, "companies": 0, "deals": 0, "tasks": 0}}

    if not type or type == "contact":
        cq = select(Contact).options(selectinload(Contact.tags)).where(
            Contact.first_name.ilike(like)
            | Contact.last_name.ilike(like)
            | Contact.email.ilike(like)
            | Contact.job_title.ilike(like)
            | Contact.notes.ilike(like)
        )
        cq = _apply_contact_ownership(cq, current_user)
        out["totals"]["contacts"] = (await db.execute(select(func.count()).select_from(cq.subquery()))).scalar() or 0
        rows = (await db.execute(cq.offset(offset).limit(limit))).scalars().all()
        out["contacts"] = [ContactRead.model_validate(c).model_dump(mode="json") for c in rows]

    if not type or type == "company":
        cq = select(Company).options(selectinload(Company.tags)).where(
            Company.name.ilike(like)
            | Company.domain.ilike(like)
            | Company.industry.ilike(like)
            | Company.address.ilike(like)
            | Company.notes.ilike(like)
        )
        cq = _apply_company_ownership(cq, current_user)
        out["totals"]["companies"] = (await db.execute(select(func.count()).select_from(cq.subquery()))).scalar() or 0
        rows = (await db.execute(cq.offset(offset).limit(limit))).scalars().all()
        out["companies"] = [CompanyRead.model_validate(c).model_dump(mode="json") for c in rows]

    if not type or type == "deal":
        dq = select(Deal).options(selectinload(Deal.tags)).where(Deal.title.ilike(like) | Deal.notes.ilike(like))
        dq = _apply_deal_ownership(dq, current_user)
        out["totals"]["deals"] = (await db.execute(select(func.count()).select_from(dq.subquery()))).scalar() or 0
        rows = (await db.execute(dq.offset(offset).limit(limit))).scalars().all()
        out["deals"] = [DealRead.model_validate(d).model_dump(mode="json") for d in rows]

    if not type or type == "task":
        tq = select(Task).where(Task.title.ilike(like) | Task.description.ilike(like))
        tq = _apply_task_ownership(tq, current_user)
        out["totals"]["tasks"] = (await db.execute(select(func.count()).select_from(tq.subquery()))).scalar() or 0
        rows = (await db.execute(tq.offset(offset).limit(limit))).scalars().all()
        out["tasks"] = [TaskRead.model_validate(t).model_dump(mode="json") for t in rows]

    return out
