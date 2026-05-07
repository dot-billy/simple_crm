import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import APIKey, User
from app.routes.notifications import add_notification
from app.schemas import APIKeyCreate, APIKeyCreated, APIKeyRead

router = APIRouter(prefix="/api/api-keys", tags=["api_keys"])


@router.get("", response_model=list[APIKeyRead])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == current_user.id, APIKey.is_active == True)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [APIKeyRead.model_validate(k) for k in keys]


@router.post("", response_model=APIKeyCreated)
async def create_api_key(
    data: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_key = secrets.token_urlsafe(32)
    prefix = raw_key[:8]
    key_hash = hash_password(raw_key)

    expires_at = None
    if data.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    api_key = APIKey(
        user_id=current_user.id,
        name=data.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    add_notification(
        db,
        user_id=current_user.id,
        title="API key created",
        message=f"A new API key '{data.name}' was created on your account. If this wasn't you, revoke it immediately.",
        entity_type="api_key",
        entity_id=api_key.id,
    )
    await db.commit()
    await db.refresh(api_key)

    return APIKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=prefix,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.delete("/{key_id}")
async def deactivate_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.is_active = False
    add_notification(
        db,
        user_id=current_user.id,
        title="API key revoked",
        message=f"API key '{api_key.name}' was revoked.",
        entity_type="api_key",
        entity_id=api_key.id,
    )
    await db.commit()
    return {"ok": True}
