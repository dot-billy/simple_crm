from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import log_mutation
from app.auth import get_current_user, require_scope
from app.catalyst_intake import is_catalyst_intake_activity, notify_catalyst_intake_slack
from app.config import settings
from app.database import get_db
from app.models import Activity, AuditEventType, Contact, Deal, EmailMessage, Task, User, UserRole
from app.routes.notifications import add_notification
from app.schemas import ActivityCreate, ActivityRead, PaginatedTimelineResponse, TimelineItem

router = APIRouter(prefix="/api/activities", tags=["activities"])
timeline_router = APIRouter(prefix="/api/contacts", tags=["timeline"])
company_timeline_router = APIRouter(prefix="/api/companies", tags=["timeline"])


@router.get("", response_model=dict)
async def list_activities(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    contact_id: UUID | None = Query(None),
    deal_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("activities:read")),
):
    query = select(Activity)
    if current_user.role == UserRole.USER:
        query = query.where(Activity.created_by == current_user.id)
    if contact_id:
        query = query.where(Activity.contact_id == contact_id)
    if deal_id:
        query = query.where(Activity.deal_id == deal_id)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = query.order_by(Activity.activity_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "items": [ActivityRead.model_validate(a) for a in items],
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.post("", response_model=ActivityRead)
async def create_activity(data: ActivityCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("activities:write"))):
    activity = Activity(**data.model_dump(), created_by=current_user.id)
    db.add(activity)
    await db.flush()
    log_mutation(db, event_type=AuditEventType.ACTIVITY_CREATED, user=current_user, entity_type="activity", entity_id=activity.id, after=activity)
    if activity.contact_id:
        contact = (await db.execute(select(Contact).where(Contact.id == activity.contact_id))).scalar_one_or_none()
        if contact and contact.owner_id and contact.owner_id != current_user.id:
            add_notification(
                db,
                user_id=contact.owner_id,
                title=f"New activity on {contact.first_name} {contact.last_name}",
                message=f"{current_user.full_name or current_user.email} logged: {activity.subject}",
                entity_type="contact",
                entity_id=contact.id,
            )
    should_notify_catalyst_intake = is_catalyst_intake_activity(activity) and activity.deal_id
    activity_id = activity.id
    await db.commit()
    if should_notify_catalyst_intake:
        intake_activity_result = await db.execute(
            select(Activity)
            .options(
                selectinload(Activity.contact),
                selectinload(Activity.deal).selectinload(Deal.company),
            )
            .where(Activity.id == activity_id)
        )
        intake_activity = intake_activity_result.scalar_one_or_none()
        if intake_activity:
            await notify_catalyst_intake_slack(
                webhook_url=settings.SLACK_WEBHOOK_URL,
                activity=intake_activity,
                deal=intake_activity.deal,
                contact=intake_activity.contact,
                company=intake_activity.deal.company if intake_activity.deal else None,
                crm_frontend_base_url=settings.CRM_FRONTEND_BASE_URL,
            )
    refreshed = await db.execute(select(Activity).where(Activity.id == activity_id))
    return refreshed.scalar_one()


@router.delete("/{activity_id}")
async def delete_activity(activity_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("activities:write"))):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if current_user.role == UserRole.USER and activity.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    before_snapshot = {c.name: getattr(activity, c.name) for c in activity.__table__.columns}
    activity_id_copy = activity.id
    await db.delete(activity)
    log_mutation(db, event_type=AuditEventType.ACTIVITY_DELETED, user=current_user, entity_type="activity", entity_id=activity_id_copy, before=before_snapshot)
    await db.commit()
    return {"ok": True}


@timeline_router.get("/{contact_id}/timeline", response_model=PaginatedTimelineResponse)
async def get_contact_timeline(
    contact_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("activities:read")),
):
    timeline_items: list[TimelineItem] = []

    # Activities for this contact
    act_q = select(Activity).where(Activity.contact_id == contact_id)
    if current_user.role == UserRole.USER:
        act_q = act_q.where(Activity.created_by == current_user.id)
    act_result = await db.execute(act_q)
    for a in act_result.scalars().all():
        timeline_items.append(TimelineItem(
            id=a.id,
            type="activity",
            title=a.subject,
            description=a.description,
            date=a.activity_date,
            metadata={"activity_type": a.type.value},
        ))

    # Emails for this contact
    email_q = select(EmailMessage).where(EmailMessage.contact_id == contact_id)
    email_result = await db.execute(email_q)
    for e in email_result.scalars().all():
        timeline_items.append(TimelineItem(
            id=e.id,
            type="email",
            title=e.subject or "(no subject)",
            description=e.snippet,
            date=e.email_date,
            metadata={"direction": e.direction.value, "from_email": e.from_email},
        ))

    # Tasks for this contact
    task_q = select(Task).where(Task.contact_id == contact_id)
    if current_user.role == UserRole.USER:
        task_q = task_q.where(Task.assigned_to == current_user.id)
    task_result = await db.execute(task_q)
    for t in task_result.scalars().all():
        timeline_items.append(TimelineItem(
            id=t.id,
            type="task",
            title=t.title,
            description=t.description,
            date=t.due_date or t.created_at,
            metadata={"status": t.status.value},
        ))

    # Sort by date descending
    timeline_items.sort(key=lambda x: x.date, reverse=True)

    total = len(timeline_items)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = timeline_items[start:end]

    return PaginatedTimelineResponse(
        items=paginated,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if per_page else 0,
    )


@company_timeline_router.get("/{company_id}/timeline", response_model=PaginatedTimelineResponse)
async def get_company_timeline(
    company_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("activities:read")),
):
    # Get contact IDs and deal IDs for this company
    contact_ids_q = select(Contact.id).where(Contact.company_id == company_id)
    contact_ids = [r[0] for r in (await db.execute(contact_ids_q)).all()]

    deal_ids_q = select(Deal.id).where(Deal.company_id == company_id)
    deal_ids = [r[0] for r in (await db.execute(deal_ids_q)).all()]

    timeline_items: list[TimelineItem] = []

    # Activities for company contacts or company deals
    if contact_ids or deal_ids:
        act_q = select(Activity)
        conditions = []
        if contact_ids:
            conditions.append(Activity.contact_id.in_(contact_ids))
        if deal_ids:
            conditions.append(Activity.deal_id.in_(deal_ids))
        from sqlalchemy import or_
        act_q = act_q.where(or_(*conditions))
        if current_user.role == UserRole.USER:
            act_q = act_q.where(Activity.created_by == current_user.id)
        for a in (await db.execute(act_q)).scalars().all():
            timeline_items.append(TimelineItem(
                id=a.id, type="activity", title=a.subject,
                description=a.description, date=a.activity_date,
                metadata={"activity_type": a.type.value},
            ))

    # Emails for company contacts
    if contact_ids:
        email_q = select(EmailMessage).where(EmailMessage.contact_id.in_(contact_ids))
        for e in (await db.execute(email_q)).scalars().all():
            timeline_items.append(TimelineItem(
                id=e.id, type="email", title=e.subject or "(no subject)",
                description=e.snippet, date=e.email_date,
                metadata={"direction": e.direction.value, "from_email": e.from_email},
            ))

    # Tasks for company contacts or company deals
    if contact_ids or deal_ids:
        task_q = select(Task)
        conditions = []
        if contact_ids:
            conditions.append(Task.contact_id.in_(contact_ids))
        if deal_ids:
            conditions.append(Task.deal_id.in_(deal_ids))
        task_q = task_q.where(or_(*conditions))
        if current_user.role == UserRole.USER:
            task_q = task_q.where(Task.assigned_to == current_user.id)
        for t in (await db.execute(task_q)).scalars().all():
            timeline_items.append(TimelineItem(
                id=t.id, type="task", title=t.title,
                description=t.description, date=t.due_date or t.created_at,
                metadata={"status": t.status.value},
            ))

    timeline_items.sort(key=lambda x: x.date, reverse=True)
    total = len(timeline_items)
    start = (page - 1) * per_page
    paginated = timeline_items[start:start + per_page]

    return PaginatedTimelineResponse(
        items=paginated, total=total, page=page, per_page=per_page,
        pages=(total + per_page - 1) // per_page if per_page else 0,
    )
