import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.auth import create_access_token, get_current_user, hash_password, require_role, verify_password
from app.config import settings
from app.database import get_db
from app.models import AccountType, AuditEventType, AuditLog, User, UserRole
from app.schemas import (
    AuditLogRead,
    PaginatedAuditLogResponse,
    PasswordChange,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
audit_logger = logging.getLogger("audit")
limiter = Limiter(key_func=get_remote_address)


async def _write_audit(
    db: AsyncSession,
    event_type: AuditEventType,
    *,
    ip_address: str | None = None,
    user_id=None,
    target_user_id=None,
    email: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        entry = AuditLog(
            event_type=event_type,
            user_id=user_id,
            target_user_id=target_user_id,
            email=email,
            ip_address=ip_address,
            detail=detail,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        logging.getLogger(__name__).exception("Failed to write audit log")


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        audit_logger.warning("LOGIN_FAILED email=%s ip=%s", form.username, ip)
        await _write_audit(db, AuditEventType.LOGIN_FAILED, ip_address=ip, email=form.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if user.account_type == AccountType.SERVICE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service accounts cannot log in via password")
    token = create_access_token(user.id, user.role.value)
    audit_logger.info("LOGIN_SUCCESS user_id=%s email=%s ip=%s", user.id, user.email, ip)
    await _write_audit(db, AuditEventType.LOGIN_SUCCESS, ip_address=ip, user_id=user.id, email=user.email)

    response = JSONResponse(content={
        "access_token": token,
        "token_type": "bearer",
        "user": UserRead.model_validate(user).model_dump(mode="json"),
    })
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@router.post("/logout")
async def logout():
    response = JSONResponse(content={"ok": True})
    response.delete_cookie("access_token", path="/")
    return response


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/password")
async def change_password(
    data: PasswordChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()
    ip = request.client.host if request.client else "unknown"
    audit_logger.info("PASSWORD_CHANGED user_id=%s ip=%s", current_user.id, ip)
    await _write_audit(db, AuditEventType.PASSWORD_CHANGED, ip_address=ip, user_id=current_user.id)
    return {"ok": True}


@router.post("/users", response_model=UserRead)
async def create_user(
    data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    ip = request.client.host if request.client else "unknown"
    audit_logger.info("USER_CREATED id=%s email=%s by=%s", user.id, user.email, current_user.id)
    await _write_audit(db, AuditEventType.USER_CREATED, ip_address=ip, user_id=current_user.id, target_user_id=user.id, email=user.email)
    return user


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(
        select(User).where(User.account_type == AccountType.HUMAN).order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    from uuid import UUID
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    ip = request.client.host if request.client else "unknown"
    audit_logger.info("USER_UPDATED id=%s by=%s", user.id, current_user.id)
    await _write_audit(db, AuditEventType.USER_UPDATED, ip_address=ip, user_id=current_user.id, target_user_id=user.id)
    return user


@router.get("/audit-log", response_model=PaginatedAuditLogResponse)
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    event_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
        count_query = count_query.where(AuditLog.event_type == event_type)
    total = (await db.execute(count_query)).scalar() or 0
    items = (await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )).scalars().all()
    return PaginatedAuditLogResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )
