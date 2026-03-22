import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.database import engine, async_session, Base
from app.gmail_sync_worker import gmail_sync_loop
from app.models import User, UserRole
from app.routes import auth, contacts, companies, deals, activities, tasks, tags, custom_fields, dashboard, email


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default admin user if none exists
    async with async_session() as db:
        result = await db.execute(select(User).where(User.role == UserRole.ADMIN))
        if not result.scalar_one_or_none():
            admin = User(
                email="admin@local.dev",
                full_name="Admin User",
                hashed_password=hash_password("admin123"),
                role=UserRole.ADMIN,
            )
            db.add(admin)
            await db.commit()

    # Start background Gmail sync worker
    sync_task = asyncio.create_task(gmail_sync_loop())

    yield

    sync_task.cancel()
    await engine.dispose()


app = FastAPI(
    title="Simple CRM",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
