import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.database import engine, async_session, Base
from app.gmail_sync_worker import gmail_sync_loop
from app.notification_worker import notification_worker_loop
from app.models import User, UserRole
from app.routes import auth, contacts, companies, deals, activities, tasks, tags, custom_fields, dashboard, email, search, notifications, api_keys, service_accounts, agent, audit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Stopgap mini-migrations until Alembic is added.
        # Idempotent: ADD VALUE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
        from sqlalchemy import text
        new_enum_values = [
            "CONTACT_CREATED", "CONTACT_UPDATED", "CONTACT_DELETED",
            "COMPANY_CREATED", "COMPANY_UPDATED", "COMPANY_DELETED",
            "DEAL_CREATED", "DEAL_UPDATED", "DEAL_DELETED", "DEAL_STAGE_CHANGED",
            "TASK_CREATED", "TASK_UPDATED", "TASK_DELETED",
            "ACTIVITY_CREATED", "ACTIVITY_DELETED",
        ]
        for v in new_enum_values:
            await conn.execute(text(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{v}'"))
        for col_def in [
            "ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50)",
            "ADD COLUMN IF NOT EXISTS entity_id UUID",
            "ADD COLUMN IF NOT EXISTS before_state TEXT",
            "ADD COLUMN IF NOT EXISTS after_state TEXT",
        ]:
            await conn.execute(text(f"ALTER TABLE audit_log {col_def}"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_log_entity_type ON audit_log(entity_type)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_log_entity_id ON audit_log(entity_id)"))
        # Task reminders / recurrence
        for col_def in [
            "ADD COLUMN IF NOT EXISTS reminder_minutes_before INTEGER",
            "ADD COLUMN IF NOT EXISTS recurrence_rule taskrecurrence NOT NULL DEFAULT 'NONE'",
            "ADD COLUMN IF NOT EXISTS parent_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL",
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE tasks {col_def}"))
            except Exception:
                # taskrecurrence enum may need creating first; create_all should handle it,
                # but if the column add races on first boot just skip and let next boot fix.
                pass
        # Deal probability
        await conn.execute(text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS probability DOUBLE PRECISION"))

    # Seed default admin user if none exists
    async with async_session() as db:
        result = await db.execute(select(User).where(User.role == UserRole.ADMIN))
        if not result.scalar_one_or_none():
            if settings.ADMIN_PASSWORD:
                admin_pw = settings.ADMIN_PASSWORD
            else:
                admin_pw = secrets.token_urlsafe(16)
                logger.warning("Generated initial admin password: %s -- change it immediately", admin_pw)
            admin = User(
                email="admin@local.dev",
                full_name="Admin User",
                hashed_password=hash_password(admin_pw),
                role=UserRole.ADMIN,
            )
            db.add(admin)
            await db.commit()

    # Start background Gmail sync worker
    sync_task = asyncio.create_task(gmail_sync_loop())
    # Start background notification worker (due-soon task scans)
    notif_task = asyncio.create_task(notification_worker_loop())

    yield

    sync_task.cancel()
    notif_task.cancel()
    await engine.dispose()


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Simple CRM",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    redirect_slashes=False,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-API-Key"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.include_router(auth.router)
app.include_router(contacts.router)
app.include_router(companies.router)
app.include_router(deals.router)
app.include_router(activities.router)
app.include_router(tasks.router)
app.include_router(tags.router)
app.include_router(custom_fields.router)
app.include_router(dashboard.router)
app.include_router(email.router)
app.include_router(search.router)
app.include_router(activities.timeline_router)
app.include_router(activities.company_timeline_router)
app.include_router(notifications.router)
app.include_router(api_keys.router)
app.include_router(service_accounts.router)
app.include_router(agent.router)
app.include_router(audit.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
