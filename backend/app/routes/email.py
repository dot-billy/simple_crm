import base64
import json
import re
import urllib.parse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_scope
from app.config import settings
from app.database import get_db
from app.gmail_service import send_email, sync_user_gmail, verify_tracking_signature
from app.models import (
    Company,
    Contact,
    Deal,
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
limiter = Limiter(key_func=get_remote_address)


# Per-user send rate limit: in-memory sliding 1-hour window keyed by user id.
import time as _time
from collections import deque as _deque
_USER_SEND_LOG: dict[str, _deque] = {}
SEND_RATE_LIMIT_PER_HOUR = 30


def _check_send_rate(user: User) -> None:
    key = str(user.id)
    now = _time.monotonic()
    window_start = now - 3600.0
    log = _USER_SEND_LOG.setdefault(key, _deque())
    while log and log[0] < window_start:
        log.popleft()
    if len(log) >= SEND_RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail=f"Send rate limit exceeded ({SEND_RATE_LIMIT_PER_HOUR}/hr)")
    log.append(now)

# Transparent 1x1 GIF pixel
TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

TEMPLATE_VARIABLES = {
    "contact": ["first_name", "last_name", "email", "phone", "job_title"],
    "company": ["name", "domain", "industry", "size"],
    "deal": ["title", "value", "currency", "stage"],
    "user": ["full_name", "email"],
}


def _substitute_variables(
    html: str,
    contact=None,
    deal=None,
    company=None,
    user=None,
) -> str:
    """Replace {{entity.field}} placeholders with actual values."""
    entities = {
        "contact": contact,
        "deal": deal,
        "company": company,
        "user": user,
    }

    def replacer(match):
        entity_name = match.group(1)
        field_name = match.group(2)
        obj = entities.get(entity_name)
        if obj is None:
            return ""
        value = getattr(obj, field_name, None)
        return str(value) if value is not None else ""

    return re.sub(r"\{\{(\w+)\.(\w+)\}\}", replacer, html)


# --- Template Variables ---

@router.get("/template-variables")
async def get_template_variables(
    current_user: User = Depends(require_scope("email:read")),
):
    return TEMPLATE_VARIABLES


@router.get("/config-status")
async def get_config_status(
    current_user: User = Depends(require_scope("email:read")),
):
    """Tell the UI whether Gmail integration is actually wired up."""
    import os
    configured = bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE) and os.path.isfile(settings.GOOGLE_SERVICE_ACCOUNT_FILE or "")
    return {
        "configured": configured,
        "credentials_path_set": bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE),
        "send_rate_limit_per_hour": SEND_RATE_LIMIT_PER_HOUR,
    }


# --- Sync ---

@router.get("/sync/status", response_model=GmailSyncStatus)
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("email:read")),
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
    current_user: User = Depends(require_scope("email:write")),
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
    current_user: User = Depends(require_scope("email:read")),
):
    query = select(EmailMessage)
    if current_user.role == UserRole.USER:
        query = query.where(EmailMessage.synced_by == current_user.id)

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
    current_user: User = Depends(require_scope("email:read")),
):
    query = select(EmailMessage).where(EmailMessage.id == email_id)
    if current_user.role == UserRole.USER:
        query = query.where(EmailMessage.synced_by == current_user.id)
    result = await db.execute(query)
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.post("/send", response_model=EmailMessageRead)
async def send(
    data: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("email:write")),
):
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        raise HTTPException(status_code=400, detail="Gmail integration not configured")
    _check_send_rate(current_user)

    # Load related entities for template variable substitution
    contact = None
    deal = None
    company = None
    if data.contact_id:
        result = await db.execute(select(Contact).where(Contact.id == data.contact_id))
        contact = result.scalar_one_or_none()
    if data.deal_id:
        result = await db.execute(select(Deal).where(Deal.id == data.deal_id))
        deal = result.scalar_one_or_none()
        if deal and deal.company_id:
            result = await db.execute(select(Company).where(Company.id == deal.company_id))
            company = result.scalar_one_or_none()
    if not company and contact and contact.company_id:
        result = await db.execute(select(Company).where(Company.id == contact.company_id))
        company = result.scalar_one_or_none()

    body_html = _substitute_variables(
        data.body_html,
        contact=contact,
        deal=deal,
        company=company,
        user=current_user,
    )

    email = await send_email(
        db=db,
        user_email=current_user.email,
        user_id=current_user.id,
        to=data.to,
        subject=data.subject,
        body_html=body_html,
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
    current_user: User = Depends(require_scope("email:write")),
):
    query = select(EmailMessage).where(EmailMessage.id == email_id)
    if current_user.role == UserRole.USER:
        query = query.where(EmailMessage.synced_by == current_user.id)
    result = await db.execute(query)
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
@limiter.limit("30/minute")
async def track_open(
    email_id: str,
    request: Request,
    sig: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Tracking pixel endpoint. Returns 1x1 GIF and logs open event."""
    try:
        if verify_tracking_signature(email_id, "", sig):
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
@limiter.limit("30/minute")
async def track_click(
    email_id: str,
    url: str,
    request: Request,
    sig: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Click tracking redirect. Logs click and redirects to original URL."""
    if not verify_tracking_signature(email_id, url, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        original_url = base64.urlsafe_b64decode(url).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Validate URL scheme to prevent open redirect to javascript: / data: etc.
    parsed = urllib.parse.urlparse(original_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

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
    current_user: User = Depends(require_scope("email:read")),
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
    current_user: User = Depends(require_scope("email:read")),
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
    current_user: User = Depends(require_scope("email:read")),
):
    query = select(EmailTemplate)
    if current_user.role == UserRole.USER:
        query = query.where(
            (EmailTemplate.created_by == current_user.id) | (EmailTemplate.created_by == None)
        )
    result = await db.execute(query.order_by(EmailTemplate.name))
    return result.scalars().all()


@router.post("/templates", response_model=EmailTemplateRead)
async def create_template(
    data: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("email:write")),
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
    current_user: User = Depends(require_scope("email:write")),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if current_user.role == UserRole.USER and template.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("email:write")),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if current_user.role == UserRole.USER and template.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.delete(template)
    await db.commit()
    return {"ok": True}


class _SampleObj:
    """Light object that mimics getattr for template substitution."""
    def __init__(self, attrs: dict):
        for k, v in attrs.items():
            setattr(self, k, v)


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("email:read")),
):
    template = (await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    sample_contact = _SampleObj({"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com", "phone": "+1 555 0100", "job_title": "VP Engineering"})
    sample_company = _SampleObj({"name": "Acme Inc.", "domain": "acme.com", "industry": "SaaS", "size": "50-100"})
    sample_deal = _SampleObj({"title": "Acme Annual Contract", "value": 25000, "currency": "USD", "stage": "proposal"})

    return {
        "subject": _substitute_variables(template.subject or "", contact=sample_contact, deal=sample_deal, company=sample_company, user=current_user),
        "body_html": _substitute_variables(template.body_html or "", contact=sample_contact, deal=sample_deal, company=sample_company, user=current_user),
    }
