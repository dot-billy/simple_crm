from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Activity, Company, Contact, Deal, DealStage, Task, TaskStatus, User, UserRole
from app.schemas import ActivityRead, DashboardStats, TaskRead

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_user = current_user.role == UserRole.USER

    # Contacts
    q = select(func.count()).select_from(Contact)
    if is_user:
        q = q.where(Contact.owner_id == current_user.id)
    total_contacts = (await db.execute(q)).scalar() or 0

    # Companies
    total_companies = (await db.execute(select(func.count()).select_from(Company))).scalar() or 0

    # Deals
    deals_q = select(Deal)
    if is_user:
        deals_q = deals_q.where(Deal.owner_id == current_user.id)

    total_deals_q = select(func.count()).select_from(deals_q.subquery())
    total_deals = (await db.execute(total_deals_q)).scalar() or 0

    value_q = select(func.coalesce(func.sum(Deal.value), 0))
    if is_user:
        value_q = value_q.where(Deal.owner_id == current_user.id)
    total_deal_value = (await db.execute(value_q)).scalar() or 0

    # Deals by stage
    stage_q = select(Deal.stage, func.count()).group_by(Deal.stage)
    if is_user:
        stage_q = stage_q.where(Deal.owner_id == current_user.id)
    stage_result = await db.execute(stage_q)
    deals_by_stage = {row[0].value: row[1] for row in stage_result.all()}

    # Recent activities
    act_q = select(Activity).order_by(Activity.activity_date.desc()).limit(10)
    recent_activities = [ActivityRead.model_validate(a) for a in (await db.execute(act_q)).scalars().all()]

    # Upcoming tasks
    now = datetime.now(timezone.utc)
    task_q = select(Task).where(
        Task.status != TaskStatus.DONE,
        Task.due_date >= now,
    ).order_by(Task.due_date.asc()).limit(10)
    if is_user:
        task_q = task_q.where(Task.assigned_to == current_user.id)
    upcoming_tasks = [TaskRead.model_validate(t) for t in (await db.execute(task_q)).scalars().all()]

    return DashboardStats(
        total_contacts=total_contacts,
        total_companies=total_companies,
        total_deals=total_deals,
        total_deal_value=float(total_deal_value),
        deals_by_stage=deals_by_stage,
        recent_activities=recent_activities,
        upcoming_tasks=upcoming_tasks,
    )
