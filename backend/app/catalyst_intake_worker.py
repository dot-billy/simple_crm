import asyncio
import logging

from app.catalyst_intake_processor import process_next_submission
from app.config import settings
from app.database import Base, async_session, engine

logger = logging.getLogger(__name__)


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run_once(
    *,
    session_factory=async_session,
    slack_webhook_url: str | None = None,
    crm_frontend_base_url: str | None = None,
) -> bool:
    async with session_factory() as db:
        return await process_next_submission(
            db,
            slack_webhook_url=slack_webhook_url if slack_webhook_url is not None else settings.SLACK_WEBHOOK_URL,
            crm_frontend_base_url=crm_frontend_base_url if crm_frontend_base_url is not None else settings.CRM_FRONTEND_BASE_URL,
        )


async def worker_loop(
    *,
    poll_seconds: float | None = None,
    session_factory=async_session,
) -> None:
    interval = poll_seconds if poll_seconds is not None else settings.CATALYST_INTAKE_WORKER_POLL_SECONDS
    await ensure_schema()
    logger.info("Starting Catalyst intake worker")
    while True:
        processed = await run_once(session_factory=session_factory)
        if not processed:
            await asyncio.sleep(interval)


def main() -> None:
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
