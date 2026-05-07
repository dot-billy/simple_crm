from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Notification, User
from app.schemas import NotificationRead, PaginatedNotificationResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def add_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notification)
    return notification


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> Notification:
    notification = add_notification(db, user_id, title, message, entity_type, entity_id)
    await db.commit()
    await db.refresh(notification)
    return notification


@router.get("", response_model=PaginatedNotificationResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_query = select(Notification).where(Notification.user_id == current_user.id)

    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    unread_q = select(func.count()).select_from(
        base_query.where(Notification.is_read == False).subquery()
    )
    unread_count = (await db.execute(unread_q)).scalar() or 0

    query = (
        base_query
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [NotificationRead.model_validate(n) for n in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
        "unread_count": unread_count,
    }


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(func.count()).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    count = result.scalar() or 0
    return {"count": count}
