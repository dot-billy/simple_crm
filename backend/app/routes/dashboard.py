import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_scope
from app.database import get_db
from app.models import Activity, AuditEventType, AuditLog, Company, Contact, Deal, DealStage, Task, TaskStatus, User, UserRole
from app.schemas import _STAGE_DEFAULT_PROBABILITY, ActivityRead, DashboardCharts, DashboardStats, TaskRead, WeeklyDealCount

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


@router.get("/pipeline-metrics")
async def get_pipeline_metrics(
    days: int = Query(90, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("dashboard:read")),
):
    is_user = current_user.role == UserRole.USER
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    closed_stages = (DealStage.CLOSED_WON, DealStage.CLOSED_LOST)

    base = select(Deal)
    if is_user:
        base = base.where(Deal.owner_id == current_user.id)

    # Win rate: closed_won / (closed_won + closed_lost) over the date range, by deal updated_at.
    closed_q = base.where(Deal.stage.in_(closed_stages), Deal.updated_at >= since)
    closed = (await db.execute(closed_q)).scalars().all()
    won = sum(1 for d in closed if d.stage == DealStage.CLOSED_WON)
    lost = sum(1 for d in closed if d.stage == DealStage.CLOSED_LOST)
    win_rate = (won / (won + lost) * 100.0) if (won + lost) else 0.0

    # Deal velocity: avg days from created_at to updated_at on closed_won deals in range.
    won_deals = [d for d in closed if d.stage == DealStage.CLOSED_WON]
    velocity_days = (
        sum((d.updated_at - d.created_at).days for d in won_deals) / len(won_deals)
        if won_deals else 0
    )

    # Forecast: sum(value * probability/100) over open deals.
    open_q = base.where(Deal.stage.notin_(closed_stages))
    open_deals = (await db.execute(open_q)).scalars().all()
    forecast = 0.0
    open_value = 0.0
    for d in open_deals:
        prob = d.probability if d.probability is not None else _STAGE_DEFAULT_PROBABILITY.get(d.stage.value, 0.0)
        forecast += (d.value or 0) * prob / 100.0
        open_value += d.value or 0

    # Funnel: counts at each stage, ordered.
    funnel = []
    for stage in DealStage:
        count_q = select(func.count()).select_from(base.where(Deal.stage == stage).subquery())
        count = (await db.execute(count_q)).scalar() or 0
        funnel.append({"stage": stage.value, "count": count})

    # Time in stage: derived from DEAL_STAGE_CHANGED audit events. For each transition,
    # measure the gap between successive stage changes for the same deal.
    audit_q = (
        select(AuditLog)
        .where(
            AuditLog.event_type == AuditEventType.DEAL_STAGE_CHANGED,
            AuditLog.entity_type == "deal",
            AuditLog.created_at >= since,
        )
        .order_by(AuditLog.entity_id, AuditLog.created_at)
    )
    audit_rows = (await db.execute(audit_q)).scalars().all()
    # deal_id -> list of (stage_after, timestamp)
    by_deal: dict = {}
    for row in audit_rows:
        try:
            after = json.loads(row.after_state) if row.after_state else {}
        except Exception:
            after = {}
        stage = after.get("stage")
        if not stage or row.entity_id is None:
            continue
        by_deal.setdefault(str(row.entity_id), []).append((stage, row.created_at))
    stage_durations: dict[str, list[float]] = {}
    for events in by_deal.values():
        for i in range(len(events) - 1):
            stage, t0 = events[i]
            _, t1 = events[i + 1]
            stage_durations.setdefault(stage, []).append((t1 - t0).total_seconds() / 86400.0)
    avg_time_in_stage = {
        s: sum(v) / len(v) for s, v in stage_durations.items() if v
    }

    return {
        "range_days": days,
        "win_rate_pct": round(win_rate, 1),
        "won_count": won,
        "lost_count": lost,
        "velocity_days": round(velocity_days, 1),
        "forecast": round(forecast, 2),
        "open_value": round(open_value, 2),
        "open_count": len(open_deals),
        "funnel": funnel,
        "avg_time_in_stage_days": {k: round(v, 1) for k, v in avg_time_in_stage.items()},
    }
