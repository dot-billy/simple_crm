import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, hash_password, require_role, verify_password
from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.schemas import TokenResponse, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/api/auth", tags=["auth"])
audit_logger = logging.getLogger("audit")
limiter = Limiter(key_func=get_remote_address)


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        audit_logger.warning("LOGIN_FAILED email=%s ip=%s", form.username, request.client.host if request.client else "unknown")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    token = create_access_token(user.id, user.role.value)
    audit_logger.info("LOGIN_SUCCESS user_id=%s email=%s ip=%s", user.id, user.email, request.client.host if request.client else "unknown")

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


@router.post("/users", response_model=UserRead)
async def create_user(
    data: UserCreate,
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
    audit_logger.info("USER_CREATED id=%s email=%s by=%s", user.id, user.email, current_user.id)
    return user


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    data: UserUpdate,
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
    audit_logger.info("USER_UPDATED id=%s by=%s", user.id, current_user.id)
    return user
