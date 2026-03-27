from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
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


@router.get("", response_model=SearchResults)
async def global_search(
    q: str = Query("", min_length=1),
    type: str | None = Query(None, pattern="^(contact|company|deal|task)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = SearchResults()

    if not type or type == "contact":
        contact_q = select(Contact).where(
            (Contact.first_name.ilike(f"%{q}%"))
            | (Contact.last_name.ilike(f"%{q}%"))
            | (Contact.email.ilike(f"%{q}%"))
        )
        contact_q = _apply_contact_ownership(contact_q, current_user)
        contact_q = contact_q.limit(10)
        contact_result = await db.execute(contact_q)
        results.contacts = [ContactRead.model_validate(c) for c in contact_result.scalars().all()]

    if not type or type == "company":
        company_q = select(Company).where(
            (Company.name.ilike(f"%{q}%")) | (Company.domain.ilike(f"%{q}%"))
        )
        company_q = _apply_company_ownership(company_q, current_user)
        company_q = company_q.limit(10)
        company_result = await db.execute(company_q)
        results.companies = [CompanyRead.model_validate(c) for c in company_result.scalars().all()]

    if not type or type == "deal":
        deal_q = select(Deal).where(Deal.title.ilike(f"%{q}%"))
        deal_q = _apply_deal_ownership(deal_q, current_user)
        deal_q = deal_q.limit(10)
        deal_result = await db.execute(deal_q)
        results.deals = [DealRead.model_validate(d) for d in deal_result.scalars().all()]

    if not type or type == "task":
        task_q = select(Task).where(
            (Task.title.ilike(f"%{q}%")) | (Task.description.ilike(f"%{q}%"))
        )
        task_q = _apply_task_ownership(task_q, current_user)
        task_q = task_q.limit(10)
        task_result = await db.execute(task_q)
        results.tasks = [TaskRead.model_validate(t) for t in task_result.scalars().all()]

    return results
