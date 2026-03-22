import base64
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.gmail_service import send_email, sync_user_gmail
from app.models import (
    EmailMessage,
    EmailTemplate,
    EmailTrackingEvent,
    EmailTrackingEventType,
    GmailSyncState,
    User,
    UserRole,
)
from app.schemas import (
    EmailMessageRead,
    EmailSendRequest,
    EmailTemplateCreate,
    EmailTemplateRead,
    EmailTemplateUpdate,
    EmailTrackingEventRead,
    EmailTrackingStats,
    GmailSyncStatus,
)

router = APIRouter(prefix="/api/email", tags=["email"])

# Transparent 1x1 GIF pixel
TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


# --- Sync ---

@router.get("/sync/status", response_model=GmailSyncStatus)
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_configured = bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE)
    result = await db.execute(
        select(GmailSyncState).where(GmailSyncState.user_id == current_user.id)
    )
    state = result.scalar_one_or_none()
    return GmailSyncStatus(
        is_configured=is_configured,
        last_sync_at=state.last_sync_at if state else None,
        is_syncing=state.is_syncing if state else False,
        history_id=state.history_id if state else None,
    )


@router.post("/sync/trigger")
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        raise HTTPException(status_code=400, detail="Gmail integration not configured")
    count = await sync_user_gmail(db, current_user.email, current_user.id)
    return {"synced": count}


# --- Messages ---

@router.get("/messages", response_model=dict)
async def list_emails(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    contact_id: UUID | None = Query(None),
    deal_id: UUID | None = Query(None),
    direction: str = Query(""),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(EmailMessage)

    if contact_id:
        query = query.where(EmailMessage.contact_id == contact_id)
    if deal_id:
        query = query.where(EmailMessage.deal_id == deal_id)
    if direction:
        query = query.where(EmailMessage.direction == direction)
    if search:
        query = query.where(
            (EmailMessage.subject.ilike(f"%{search}%"))
            | (EmailMessage.from_email.ilike(f"%{search}%"))
            | (EmailMessage.snippet.ilike(f"%{search}%"))
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(EmailMessage.email_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [EmailMessageRead.model_validate(e) for e in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/messages/{email_id}", response_model=EmailMessageRead)
async def get_email(
    email_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EmailMessage).where(EmailMessage.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.post("/send", response_model=EmailMessageRead)
async def send(
    data: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        raise HTTPException(status_code=400, detail="Gmail integration not configured")
    email = await send_email(
        db=db,
        user_email=current_user.email,
        user_id=current_user.id,
        to=data.to,
        subject=data.subject,
        body_html=data.body_html,
        cc=data.cc,
        contact_id=data.contact_id,
        deal_id=data.deal_id,
        enable_tracking=data.enable_tracking,
    )
    return email


@router.patch("/messages/{email_id}/link")
async def link_email_to_entity(
    email_id: UUID,
    contact_id: UUID | None = None,
    deal_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(EmailMessage).where(EmailMessage.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    if contact_id is not None:
        email.contact_id = contact_id
    if deal_id is not None:
        email.deal_id = deal_id
    await db.commit()
    return {"ok": True}


# --- Tracking (public endpoints - no auth) ---

@router.get("/track/open/{email_id}")
async def track_open(
    email_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Tracking pixel endpoint. Returns 1x1 GIF and logs open event."""
    try:
        result = await db.execute(
            select(EmailMessage).where(EmailMessage.id == UUID(email_id))
        )
        email = result.scalar_one_or_none()
        if email:
            event = EmailTrackingEvent(
                email_id=email.id,
                event_type=EmailTrackingEventType.OPENED,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.add(event)
            await db.commit()
    except Exception:
        pass  # Don't break the pixel even if tracking fails

    return Response(content=TRACKING_PIXEL, media_type="image/gif")


@router.get("/track/click/{email_id}")
async def track_click(
    email_id: str,
    url: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Click tracking redirect. Logs click and redirects to original URL."""
    try:
        original_url = base64.urlsafe_b64decode(url).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        result = await db.execute(
            select(EmailMessage).where(EmailMessage.id == UUID(email_id))
        )
        email = result.scalar_one_or_none()
        if email:
            event = EmailTrackingEvent(
                email_id=email.id,
                event_type=EmailTrackingEventType.CLICKED,
                url=original_url,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.add(event)
            await db.commit()
    except Exception:
        pass

    return RedirectResponse(url=original_url)


# --- Tracking stats ---

@router.get("/messages/{email_id}/tracking", response_model=list[EmailTrackingEventRead])
async def get_tracking_events(
    email_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EmailTrackingEvent)
        .where(EmailTrackingEvent.email_id == email_id)
        .order_by(EmailTrackingEvent.created_at.desc())
    )
    return result.scalars().all()


@router.get("/tracking/stats", response_model=EmailTrackingStats)
async def get_tracking_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Count outbound emails with tracking
    sent_q = select(func.count()).select_from(EmailMessage).where(
        EmailMessage.direction == "outbound",
        EmailMessage.has_tracking_pixel == True,
    )
    total_sent = (await db.execute(sent_q)).scalar() or 0

    # Count unique opens
    opened_q = select(func.count(func.distinct(EmailTrackingEvent.email_id))).where(
        EmailTrackingEvent.event_type == EmailTrackingEventType.OPENED,
    )
    total_opened = (await db.execute(opened_q)).scalar() or 0

    # Count unique clicks
    clicked_q = select(func.count(func.distinct(EmailTrackingEvent.email_id))).where(
        EmailTrackingEvent.event_type == EmailTrackingEventType.CLICKED,
    )
    total_clicked = (await db.execute(clicked_q)).scalar() or 0

    return EmailTrackingStats(
        total_sent=total_sent,
        total_opened=total_opened,
        total_clicked=total_clicked,
        open_rate=(total_opened / total_sent * 100) if total_sent > 0 else 0,
        click_rate=(total_clicked / total_sent * 100) if total_sent > 0 else 0,
    )


# --- Templates ---

@router.get("/templates", response_model=list[EmailTemplateRead])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(EmailTemplate).order_by(EmailTemplate.name))
    return result.scalars().all()


@router.post("/templates", response_model=EmailTemplateRead)
async def create_template(
    data: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = EmailTemplate(**data.model_dump(), created_by=current_user.id)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=EmailTemplateRead)
async def update_template(
    template_id: UUID,
    data: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    await db.commit()
    return {"ok": True}
