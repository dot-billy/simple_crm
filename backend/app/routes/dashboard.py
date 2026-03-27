from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_scope
from app.database import get_db
from app.models import Activity, Company, Contact, Deal, DealStage, Task, TaskStatus, User, UserRole
from app.schemas import ActivityRead, DashboardCharts, DashboardStats, TaskRead, WeeklyDealCount

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("dashboard:read")),
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

    # --- Chart data ---

    # Deals over time (last 12 weeks)
    twelve_weeks_ago = now - timedelta(weeks=12)
    deals_time_q = select(
        func.to_char(Deal.created_at, 'IYYY-IW').label('week'),
        func.count().label('count'),
    ).where(Deal.created_at >= twelve_weeks_ago).group_by('week').order_by('week')
    if is_user:
        deals_time_q = deals_time_q.where(Deal.owner_id == current_user.id)
    deals_time_result = await db.execute(deals_time_q)
    deals_over_time = [
        WeeklyDealCount(week=row.week, count=row.count)
        for row in deals_time_result.all()
    ]

    # Revenue by stage
    rev_stage_q = select(Deal.stage, func.coalesce(func.sum(Deal.value), 0))
    if is_user:
        rev_stage_q = rev_stage_q.where(Deal.owner_id == current_user.id)
    rev_stage_q = rev_stage_q.group_by(Deal.stage)
    rev_stage_result = await db.execute(rev_stage_q)
    revenue_by_stage = {row[0].value: float(row[1]) for row in rev_stage_result.all()}

    # Contacts by source
    source_q = select(Contact.source, func.count()).where(Contact.source.isnot(None)).group_by(Contact.source)
    if is_user:
        source_q = source_q.where(Contact.owner_id == current_user.id)
    source_result = await db.execute(source_q)
    contacts_by_source = {row[0]: row[1] for row in source_result.all()}

    # Task completion
    completed_q = select(func.count()).select_from(Task).where(Task.status == TaskStatus.DONE)
    pending_q = select(func.count()).select_from(Task).where(Task.status != TaskStatus.DONE)
    if is_user:
        completed_q = completed_q.where(Task.assigned_to == current_user.id)
        pending_q = pending_q.where(Task.assigned_to == current_user.id)
    completed = (await db.execute(completed_q)).scalar() or 0
    pending = (await db.execute(pending_q)).scalar() or 0

    charts = DashboardCharts(
        deals_over_time=deals_over_time,
        revenue_by_stage=revenue_by_stage,
        contacts_by_source=contacts_by_source,
        task_completion={"completed": completed, "pending": pending},
    )

    return DashboardStats(
        total_contacts=total_contacts,
        total_companies=total_companies,
        total_deals=total_deals,
        total_deal_value=float(total_deal_value),
        deals_by_stage=deals_by_stage,
        recent_activities=recent_activities,
        upcoming_tasks=upcoming_tasks,
        charts=charts,
    )
