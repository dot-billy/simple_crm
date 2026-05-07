import csv
import io
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import log_mutation
from app.auth import get_current_user, require_role, require_scope
from app.database import get_db
from app.models import Activity, ActivityType, AuditEventType, Company, Contact, Deal, DealStage, Tag, Task, TaskStatus, User, UserRole
from app.routes.notifications import add_notification
from app.schemas import (
    ActivityRead,
    BulkAction,
    CompanyRead,
    ContactRead,
    CustomFieldDefinitionRead,
    CustomFieldValueRead,
    DealCreate,
    DealProfile,
    DealRead,
    DealStageUpdate,
    DealStats,
    DealUpdate,
    TaskRead,
)

router = APIRouter(prefix="/api/deals", tags=["deals"])


def _apply_ownership_filter(query, user: User):
    if user.role == UserRole.USER:
        query = query.where(Deal.owner_id == user.id)
    return query


@router.get("", response_model=dict)
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    stage: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("deals:read")),
):
    query = select(Deal).options(selectinload(Deal.tags))
    query = _apply_ownership_filter(query, current_user)
    if search:
        query = query.where(Deal.title.ilike(f"%{search}%"))
    if stage:
        query = query.where(Deal.stage == stage)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = query.order_by(Deal.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "items": [DealRead.model_validate(d) for d in items],
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/{deal_id}", response_model=DealRead)
async def get_deal(deal_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("deals:read"))):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("", response_model=DealRead)
async def create_deal(data: DealCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("deals:write"))):
    deal = Deal(**data.model_dump(exclude={"tag_ids"}), owner_id=current_user.id)
    if data.tag_ids:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        deal.tags = list(tags)
    db.add(deal)
    await db.flush()
    log_mutation(db, event_type=AuditEventType.DEAL_CREATED, user=current_user, entity_type="deal", entity_id=deal.id, after=deal)
    await db.commit()
    await db.refresh(deal, ["tags"])
    return deal


@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal(deal_id: UUID, data: DealUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("deals:write"))):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    before_snapshot = {c.name: getattr(deal, c.name) for c in deal.__table__.columns}
    old_owner_id = deal.owner_id
    for field, value in data.model_dump(exclude_unset=True, exclude={"tag_ids"}).items():
        setattr(deal, field, value)
    if data.tag_ids is not None:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        deal.tags = list(tags)
    log_mutation(db, event_type=AuditEventType.DEAL_UPDATED, user=current_user, entity_type="deal", entity_id=deal.id, before=before_snapshot, after=deal)
    if (
        deal.owner_id
        and deal.owner_id != old_owner_id
        and deal.owner_id != current_user.id
    ):
        add_notification(
            db,
            user_id=deal.owner_id,
            title=f"Deal assigned to you: {deal.title}",
            message=f"{current_user.full_name or current_user.email} assigned this deal to you.",
            entity_type="deal",
            entity_id=deal.id,
        )
    await db.commit()
    refreshed = await db.execute(select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal.id))
    return refreshed.scalar_one()


@router.delete("/{deal_id}")
async def delete_deal(deal_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("deals:write"))):
    query = select(Deal).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    before_snapshot = {c.name: getattr(deal, c.name) for c in deal.__table__.columns}
    deal_id_copy = deal.id
    await db.delete(deal)
    log_mutation(db, event_type=AuditEventType.DEAL_DELETED, user=current_user, entity_type="deal", entity_id=deal_id_copy, before=before_snapshot)
    await db.commit()
    return {"ok": True}


@router.patch("/{deal_id}/stage", response_model=DealRead)
async def update_deal_stage(
    deal_id: UUID,
    data: DealStageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("deals:write")),
):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    old_stage = deal.stage
    deal.stage = data.stage
    activity = Activity(
        type=ActivityType.NOTE,
        subject=f"Deal moved to {data.stage.value}",
        deal_id=deal.id,
        created_by=current_user.id,
    )
    db.add(activity)
    if old_stage != data.stage:
        log_mutation(
            db,
            event_type=AuditEventType.DEAL_STAGE_CHANGED,
            user=current_user,
            entity_type="deal",
            entity_id=deal.id,
            before={"stage": old_stage.value},
            after={"stage": data.stage.value},
        )
    if deal.owner_id and deal.owner_id != current_user.id and old_stage != data.stage:
        if data.stage == DealStage.CLOSED_WON:
            title = f"Deal won: {deal.title}"
        elif data.stage == DealStage.CLOSED_LOST:
            title = f"Deal lost: {deal.title}"
        else:
            title = f"Deal stage changed: {deal.title}"
        add_notification(
            db,
            user_id=deal.owner_id,
            title=title,
            message=f"{current_user.full_name or current_user.email} moved this deal from {old_stage.value} to {data.stage.value}.",
            entity_type="deal",
            entity_id=deal.id,
        )
    await db.commit()
    refreshed = await db.execute(select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal.id))
    return refreshed.scalar_one()


@router.get("/{deal_id}/profile", response_model=DealProfile)
async def get_deal_profile(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("deals:read")),
):
    query = (
        select(Deal)
        .options(
            selectinload(Deal.tags),
            selectinload(Deal.contact).selectinload(Contact.tags),
            selectinload(Deal.company).selectinload(Company.tags),
            selectinload(Deal.tasks),
        )
        .where(Deal.id == deal_id)
    )
    query = _apply_ownership_filter(query, current_user)
    deal = (await db.execute(query)).scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    activities = (
        await db.execute(
            select(Activity)
            .where(Activity.deal_id == deal_id)
            .order_by(Activity.activity_date.desc())
        )
    ).scalars().all()

    tasks = deal.tasks or []
    last_act_date = activities[0].activity_date if activities else None

    now = datetime.now(timezone.utc)
    days_open = (now - deal.created_at).days if deal.created_at else 0
    last_stage_change = next(
        (a.activity_date for a in activities if a.subject and a.subject.startswith("Deal moved to")),
        None,
    )
    days_in_stage = (now - last_stage_change).days if last_stage_change else days_open

    stats = DealStats(
        total_activities=len(activities),
        total_tasks=len(tasks),
        open_tasks=sum(1 for t in tasks if t.status != TaskStatus.DONE),
        days_in_stage=days_in_stage,
        days_open=days_open,
        last_activity_date=last_act_date,
    )

    return DealProfile(
        deal=DealRead.model_validate(deal),
        contact=ContactRead.model_validate(deal.contact) if deal.contact else None,
        company=CompanyRead.model_validate(deal.company) if deal.company else None,
        activities=[ActivityRead.model_validate(a) for a in activities],
        tasks=[TaskRead.model_validate(t) for t in tasks],
        custom_fields=[],
        custom_field_definitions=[],
        stats=stats,
    )


@router.post("/bulk")
async def bulk_deals(
    data: BulkAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("deals:write")),
):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id.in_(data.ids))
    query = _apply_ownership_filter(query, current_user)
    deals = (await db.execute(query)).scalars().all()
    affected = 0
    for d in deals:
        before = {col.name: getattr(d, col.name) for col in d.__table__.columns}
        if data.action == "delete":
            did = d.id
            await db.delete(d)
            log_mutation(db, event_type=AuditEventType.DEAL_DELETED, user=current_user, entity_type="deal", entity_id=did, before=before)
        elif data.action == "add_tag" and data.tag_id:
            tag = (await db.execute(select(Tag).where(Tag.id == data.tag_id))).scalar_one_or_none()
            if tag and tag not in d.tags:
                d.tags.append(tag)
                log_mutation(db, event_type=AuditEventType.DEAL_UPDATED, user=current_user, entity_type="deal", entity_id=d.id, before=before, after=d)
        elif data.action == "remove_tag" and data.tag_id:
            d.tags = [t for t in d.tags if t.id != data.tag_id]
            log_mutation(db, event_type=AuditEventType.DEAL_UPDATED, user=current_user, entity_type="deal", entity_id=d.id, before=before, after=d)
        elif data.action == "set_owner":
            d.owner_id = data.owner_id
            log_mutation(db, event_type=AuditEventType.DEAL_UPDATED, user=current_user, entity_type="deal", entity_id=d.id, before=before, after=d)
        elif data.action == "set_stage" and data.stage:
            old = d.stage
            d.stage = data.stage
            log_mutation(db, event_type=AuditEventType.DEAL_STAGE_CHANGED, user=current_user, entity_type="deal", entity_id=d.id, before={"stage": old.value}, after={"stage": data.stage.value})
        else:
            continue
        affected += 1
    await db.commit()
    return {"affected": affected}


def _sanitize_csv_value(val: str | None) -> str | None:
    if not val:
        return val
    return val.lstrip("=+-@")


@router.post("/import/csv")
async def import_deals_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_ROWS = 10000
    raw = await file.read(MAX_SIZE + 1)
    if len(raw) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")
    content = raw.decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    skipped = 0
    valid_stages = {s.value for s in DealStage}
    for row in reader:
        if imported + skipped >= MAX_ROWS:
            break
        stage_str = _sanitize_csv_value(row.get("stage", "")) or ""
        if stage_str not in valid_stages:
            skipped += 1
            continue
        title = _sanitize_csv_value(row.get("title", "")) or ""
        if not title:
            skipped += 1
            continue
        value_str = _sanitize_csv_value(row.get("value", "")) or "0"
        try:
            value = float(value_str)
        except ValueError:
            value = 0
        expected_close_date = None
        date_str = _sanitize_csv_value(row.get("expected_close_date", "")) or ""
        if date_str:
            try:
                expected_close_date = datetime.fromisoformat(date_str)
            except ValueError:
                pass
        deal = Deal(
            title=title,
            value=value,
            currency=_sanitize_csv_value(row.get("currency", "")) or "USD",
            stage=DealStage(stage_str),
            expected_close_date=expected_close_date,
            notes=_sanitize_csv_value(row.get("notes")),
            owner_id=current_user.id,
        )
        db.add(deal)
        imported += 1
    await db.commit()
    return {"imported": imported, "skipped": skipped}
