import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.gmail_service import sync_user_gmail
from app.models import User

logger = logging.getLogger(__name__)


async def gmail_sync_loop():
    """Background loop that periodically syncs Gmail for all active users."""
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        logger.info("Gmail integration not configured, sync worker disabled")
        return

    logger.info(
        "Gmail sync worker started (interval: %ds)",
        settings.GMAIL_SYNC_INTERVAL_SECONDS,
    )

    while True:
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(User).where(User.is_active == True)
                )
                users = result.scalars().all()

                for user in users:
                    try:
                        count = await sync_user_gmail(db, user.email, user.id)
                        if count > 0:
                            logger.info("Synced %d emails for %s", count, user.email)
                    except Exception as e:
                        logger.error("Sync failed for %s: %s", user.email, e)

        except Exception as e:
            logger.error("Gmail sync loop error: %s", e)

        await asyncio.sleep(settings.GMAIL_SYNC_INTERVAL_SECONDS)
