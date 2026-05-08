import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user_session
from app.database import get_db
from app.models import SavedView, User
from app.schemas import SavedViewCreate, SavedViewRead, SavedViewUpdate

router = APIRouter(prefix="/api/saved-views", tags=["saved_views"])


def _to_read(sv: SavedView) -> SavedViewRead:
    return SavedViewRead(
        id=sv.id,
        user_id=sv.user_id,
        entity_type=sv.entity_type,
        name=sv.name,
        filters=json.loads(sv.filters) if sv.filters else {},
        is_shared=sv.is_shared,
        created_at=sv.created_at,
    )


@router.get("", response_model=list[SavedViewRead])
async def list_saved_views(
    entity_type: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_session),
):
    query = select(SavedView).where(
        or_(SavedView.user_id == current_user.id, SavedView.is_shared == True)
    )
    if entity_type:
        query = query.where(SavedView.entity_type == entity_type)
    query = query.order_by(SavedView.created_at.desc())
    rows = (await db.execute(query)).scalars().all()
    return [_to_read(sv) for sv in rows]


@router.post("", response_model=SavedViewRead)
async def create_saved_view(
    data: SavedViewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_session),
):
    sv = SavedView(
        user_id=current_user.id,
        entity_type=data.entity_type,
        name=data.name,
        filters=json.dumps(data.filters),
        is_shared=data.is_shared,
    )
    db.add(sv)
    await db.commit()
    await db.refresh(sv)
    return _to_read(sv)


@router.patch("/{view_id}", response_model=SavedViewRead)
async def update_saved_view(
    view_id: UUID,
    data: SavedViewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_session),
):
    sv = (await db.execute(select(SavedView).where(SavedView.id == view_id))).scalar_one_or_none()
    if not sv:
        raise HTTPException(status_code=404, detail="View not found")
    if sv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your view")
    if data.name is not None:
        sv.name = data.name
    if data.filters is not None:
        sv.filters = json.dumps(data.filters)
    if data.is_shared is not None:
        sv.is_shared = data.is_shared
    await db.commit()
    await db.refresh(sv)
    return _to_read(sv)


@router.delete("/{view_id}")
async def delete_saved_view(
    view_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_session),
):
    sv = (await db.execute(select(SavedView).where(SavedView.id == view_id))).scalar_one_or_none()
    if not sv:
        raise HTTPException(status_code=404, detail="View not found")
    if sv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your view")
    await db.delete(sv)
    await db.commit()
    return {"ok": True}
