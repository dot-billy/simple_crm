from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Deal, Tag, User, UserRole
from app.schemas import DealCreate, DealRead, DealUpdate

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
