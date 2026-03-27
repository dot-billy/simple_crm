import json
import logging
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, hash_password, require_role
from app.database import get_db
from app.models import (
    AccountType,
    APIKey,
    APIKeyScope,
    AuditEventType,
    AuditLog,
    User,
    UserRole,
)
from app.schemas import (
    APIKeyCreated,
    APIKeyRead,
    ScopedAPIKeyCreate,
    ServiceAccountCreate,
    ServiceAccountRead,
    ServiceAccountUpdate,
)

router = APIRouter(prefix="/api/service-accounts", tags=["service-accounts"])
logger = logging.getLogger(__name__)

VALID_SCOPES = {s.value for s in APIKeyScope}


def _sanitize_email_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:50] or "service"


async def _write_audit(
    db: AsyncSession,
    event_type: AuditEventType,
    *,
    ip_address: str | None = None,
    user_id=None,
    target_user_id=None,
    detail: str | None = None,
    api_key_id=None,
) -> None:
    try:
        entry = AuditLog(
            event_type=event_type,
            user_id=user_id,
            target_user_id=target_user_id,
            ip_address=ip_address,
            detail=detail,
            api_key_id=api_key_id,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        logger.exception("Failed to write audit log")


@router.post("/", response_model=ServiceAccountRead)
async def create_service_account(
    data: ServiceAccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    slug = _sanitize_email_slug(data.name)
    email = f"svc-{slug}@agent.local"
    # Ensure unique email
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        # Append random suffix
        email = f"svc-{slug}-{secrets.token_hex(3)}@agent.local"

    svc = User(
        email=email,
        full_name=data.name,
        hashed_password=hash_password(secrets.token_urlsafe(32)),  # dummy, can't login
        role=UserRole.USER,
        account_type=AccountType.SERVICE,
        description=data.description,
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.SERVICE_ACCOUNT_CREATED,
        ip_address=ip,
        user_id=current_user.id,
        target_user_id=svc.id,
        detail=f"Created service account: {data.name}",
    )

    return ServiceAccountRead(
        id=svc.id,
        full_name=svc.full_name,
        email=svc.email,
        description=svc.description,
        account_type=svc.account_type,
        is_active=svc.is_active,
        created_at=svc.created_at,
        key_count=0,
    )


@router.get("/", response_model=list[ServiceAccountRead])
async def list_service_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(User)
        .where(User.account_type == AccountType.SERVICE)
        .order_by(User.created_at.desc())
    )
    accounts = result.scalars().all()

    # Get key counts
    out = []
    for acct in accounts:
        count_result = await db.execute(
            select(func.count(APIKey.id)).where(
                APIKey.user_id == acct.id, APIKey.is_active == True
            )
        )
        key_count = count_result.scalar() or 0
        out.append(
            ServiceAccountRead(
                id=acct.id,
                full_name=acct.full_name,
                email=acct.email,
                description=acct.description,
                account_type=acct.account_type,
                is_active=acct.is_active,
                created_at=acct.created_at,
                key_count=key_count,
            )
        )
    return out


@router.get("/{account_id}", response_model=ServiceAccountRead)
async def get_service_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(User).where(User.id == account_id, User.account_type == AccountType.SERVICE)
    )
    acct = result.scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Service account not found")

    count_result = await db.execute(
        select(func.count(APIKey.id)).where(
            APIKey.user_id == acct.id, APIKey.is_active == True
        )
    )
    key_count = count_result.scalar() or 0

    return ServiceAccountRead(
        id=acct.id,
        full_name=acct.full_name,
        email=acct.email,
        description=acct.description,
        account_type=acct.account_type,
        is_active=acct.is_active,
        created_at=acct.created_at,
        key_count=key_count,
    )


@router.patch("/{account_id}", response_model=ServiceAccountRead)
async def update_service_account(
    account_id: UUID,
    data: ServiceAccountUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(User).where(User.id == account_id, User.account_type == AccountType.SERVICE)
    )
    acct = result.scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Service account not found")

    updates = data.model_dump(exclude_unset=True)
    if "name" in updates:
        acct.full_name = updates.pop("name")
    for field, value in updates.items():
        setattr(acct, field, value)
    await db.commit()
    await db.refresh(acct)

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.SERVICE_ACCOUNT_UPDATED,
        ip_address=ip,
        user_id=current_user.id,
        target_user_id=acct.id,
        detail=f"Updated service account: {acct.full_name}",
    )

    count_result = await db.execute(
        select(func.count(APIKey.id)).where(
            APIKey.user_id == acct.id, APIKey.is_active == True
        )
    )
    key_count = count_result.scalar() or 0

    return ServiceAccountRead(
        id=acct.id,
        full_name=acct.full_name,
        email=acct.email,
        description=acct.description,
        account_type=acct.account_type,
        is_active=acct.is_active,
        created_at=acct.created_at,
        key_count=key_count,
    )


@router.delete("/{account_id}")
async def deactivate_service_account(
    account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(User).where(User.id == account_id, User.account_type == AccountType.SERVICE)
    )
    acct = result.scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Service account not found")

    acct.is_active = False
    await db.commit()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.SERVICE_ACCOUNT_UPDATED,
        ip_address=ip,
        user_id=current_user.id,
        target_user_id=acct.id,
        detail=f"Deactivated service account: {acct.full_name}",
    )
    return {"ok": True}


# --- API Key management for service accounts ---


@router.post("/{account_id}/keys", response_model=APIKeyCreated)
async def create_service_account_key(
    account_id: UUID,
    data: ScopedAPIKeyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    # Validate service account exists
    result = await db.execute(
        select(User).where(User.id == account_id, User.account_type == AccountType.SERVICE)
    )
    acct = result.scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Service account not found")

    # Validate scopes
    for scope in data.scopes:
        if scope not in VALID_SCOPES:
            raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}")

    raw_key = secrets.token_urlsafe(32)
    prefix = raw_key[:8]

    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    api_key = APIKey(
        user_id=account_id,
        name=data.name,
        key_prefix=prefix,
        key_hash=hash_password(raw_key),
        scopes=json.dumps(data.scopes),
        expires_at=expires_at,
        rate_limit_per_minute=data.rate_limit_per_minute,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.API_KEY_CREATED,
        ip_address=ip,
        user_id=current_user.id,
        target_user_id=account_id,
        api_key_id=api_key.id,
        detail=f"Created API key '{data.name}' for service account '{acct.full_name}' with scopes: {data.scopes}",
    )

    return APIKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=prefix,
        scopes=data.scopes,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("/{account_id}/keys", response_model=list[APIKeyRead])
async def list_service_account_keys(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    # Validate service account exists
    result = await db.execute(
        select(User).where(User.id == account_id, User.account_type == AccountType.SERVICE)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Service account not found")

    keys_result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == account_id, APIKey.is_active == True)
        .order_by(APIKey.created_at.desc())
    )
    return keys_result.scalars().all()


@router.delete("/{account_id}/keys/{key_id}")
async def revoke_service_account_key(
    account_id: UUID,
    key_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id, APIKey.user_id == account_id, APIKey.is_active == True
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db.commit()

    ip = request.client.host if request.client else "unknown"
    await _write_audit(
        db,
        AuditEventType.API_KEY_REVOKED,
        ip_address=ip,
        user_id=current_user.id,
        target_user_id=account_id,
        api_key_id=api_key.id,
        detail=f"Revoked API key '{api_key.name}'",
    )
    return {"ok": True}
