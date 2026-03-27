from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Activity, EmailMessage, Task, User, UserRole
from app.schemas import ActivityCreate, ActivityRead, PaginatedTimelineResponse, TimelineItem

router = APIRouter(prefix="/api/activities", tags=["activities"])
timeline_router = APIRouter(prefix="/api/contacts", tags=["timeline"])


@router.get("", response_model=dict)
async def list_activities(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    contact_id: UUID | None = Query(None),
    deal_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
async def create_activity(data: ActivityCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    activity = Activity(**data.model_dump(), created_by=current_user.id)
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity


@router.delete("/{activity_id}")
async def delete_activity(activity_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if current_user.role == UserRole.USER and activity.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.delete(activity)
    await db.commit()
    return {"ok": True}


@timeline_router.get("/{contact_id}/timeline", response_model=PaginatedTimelineResponse)
async def get_contact_timeline(
    contact_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
