import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Activity, ActivityType, Deal, DealStage, Tag, User, UserRole
from app.schemas import DealCreate, DealRead, DealStageUpdate, DealUpdate

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
    current_user: User = Depends(get_current_user),
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
async def get_deal(deal_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("", response_model=DealRead)
async def create_deal(data: DealCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    deal = Deal(**data.model_dump(exclude={"tag_ids"}), owner_id=current_user.id)
    if data.tag_ids:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        deal.tags = list(tags)
    db.add(deal)
    await db.commit()
    await db.refresh(deal, ["tags"])
    return deal


@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal(deal_id: UUID, data: DealUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    for field, value in data.model_dump(exclude_unset=True, exclude={"tag_ids"}).items():
        setattr(deal, field, value)
    if data.tag_ids is not None:
        tags = (await db.execute(select(Tag).where(Tag.id.in_(data.tag_ids)))).scalars().all()
        deal.tags = list(tags)
    await db.commit()
    await db.refresh(deal, ["tags"])
    return deal


@router.delete("/{deal_id}")
async def delete_deal(deal_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Deal).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    await db.delete(deal)
    await db.commit()
    return {"ok": True}


@router.patch("/{deal_id}/stage", response_model=DealRead)
async def update_deal_stage(
    deal_id: UUID,
    data: DealStageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Deal).options(selectinload(Deal.tags)).where(Deal.id == deal_id)
    query = _apply_ownership_filter(query, current_user)
    result = await db.execute(query)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    deal.stage = data.stage
    activity = Activity(
        type=ActivityType.NOTE,
        subject=f"Deal moved to {data.stage.value}",
        deal_id=deal.id,
        created_by=current_user.id,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(deal, ["tags"])
    return deal


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
