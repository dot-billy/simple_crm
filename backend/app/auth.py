import time
from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AccountType, APIKey, User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# In-memory sliding-window rate limit per API key id.
# Maps api_key_id (str) -> deque of timestamps (seconds, monotonic).
# Single-process only; if we ever scale horizontally swap for Redis.
_api_key_request_log: dict[str, deque[float]] = {}


def _check_api_key_rate_limit(api_key: APIKey) -> None:
    if not api_key.rate_limit_per_minute:
        return
    key = str(api_key.id)
    now = time.monotonic()
    window_start = now - 60.0
    log = _api_key_request_log.setdefault(key, deque())
    while log and log[0] < window_start:
        log.popleft()
    if len(log) >= api_key.rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"API key rate limit exceeded ({api_key.rate_limit_per_minute}/min)",
        )
    log.append(now)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check for API key auth via X-API-Key header
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        if len(api_key_header) < 8:
            raise credentials_exception
        prefix = api_key_header[:8]
        result = await db.execute(
            select(APIKey).where(APIKey.key_prefix == prefix, APIKey.is_active == True)
        )
        candidates = result.scalars().all()
        for candidate in candidates:
            if verify_password(api_key_header, candidate.key_hash):
                # Check expiry
                if candidate.expires_at and candidate.expires_at < datetime.now(timezone.utc):
                    raise credentials_exception
                # Enforce per-key rate limit before recording usage.
                _check_api_key_rate_limit(candidate)
                # Update last_used_at
                candidate.last_used_at = datetime.now(timezone.utc)
                await db.commit()
                # Load associated user
                user_result = await db.execute(select(User).where(User.id == candidate.user_id))
                user = user_result.scalar_one_or_none()
                if user is None or not user.is_active:
                    raise credentials_exception
                # Attach the resolved API key to request state for scope checking
                request.state.api_key = candidate
                return user
        raise credentials_exception

    # Try Bearer header first, fall back to HttpOnly cookie
    auth_token = token or request.cookies.get("access_token")
    if not auth_token:
        raise credentials_exception

    try:
        payload = jwt.decode(auth_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    # No API key for JWT/cookie auth
    request.state.api_key = None
    return user


def require_role(*roles: UserRole):
    """Block API keys outright -- role-gated routes are interactive only."""
    async def checker(request: Request, current_user: User = Depends(get_current_user)) -> User:
        if getattr(request.state, "api_key", None) is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API keys cannot access role-gated endpoints",
            )
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return checker


async def require_user_session(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """For endpoints that must never be reachable via API key (e.g. API-key management itself)."""
    if getattr(request.state, "api_key", None) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API keys cannot access this endpoint; sign in interactively.",
        )
    return current_user


def require_scope(*scopes: str):
    """Check API key scopes. JWT/cookie auth passes through with full access."""
    async def checker(request: Request, current_user: User = Depends(get_current_user)) -> User:
        import json
        api_key = getattr(request.state, "api_key", None)
        if api_key is None:
            # JWT/cookie auth -- full access
            return current_user
        # API keys must have explicit scopes. NULL or empty == zero access.
        if not api_key.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has no scopes assigned",
            )
        key_scopes = json.loads(api_key.scopes)
        if "*" in key_scopes:
            return current_user
        for scope in scopes:
            if scope not in key_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key missing required scope: {scope}",
                )
        return current_user
    return checker
