import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, select

from app.database import async_session
from app.models import Notification, Task, TaskStatus

logger = logging.getLogger(__name__)

DUE_SOON_INTERVAL_SECONDS = 900  # 15 minutes
DUE_SOON_WINDOW_HOURS = 24
DUE_SOON_TITLE_PREFIX = "Task due soon"


async def _scan_due_soon_tasks() -> int:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=DUE_SOON_WINDOW_HOURS)

    async with async_session() as db:
        notif_exists = (
            select(Notification.id)
            .where(
                Notification.entity_type == "task",
                Notification.entity_id == Task.id,
                Notification.title.like(f"{DUE_SOON_TITLE_PREFIX}%"),
            )
            .exists()
        )
        query = select(Task).where(
            Task.status != TaskStatus.DONE,
            Task.assigned_to.isnot(None),
            Task.due_date.isnot(None),
            Task.due_date <= cutoff,
            Task.due_date > now,
            ~notif_exists,
        )
        tasks = (await db.execute(query)).scalars().all()
        for task in tasks:
            db.add(
                Notification(
                    user_id=task.assigned_to,
                    title=f"{DUE_SOON_TITLE_PREFIX}: {task.title}",
                    message=f"This task is due {task.due_date.isoformat()}.",
                    entity_type="task",
                    entity_id=task.id,
                )
            )
        if tasks:
            await db.commit()
        return len(tasks)


async def notification_worker_loop():
    logger.info("Notification worker started (interval: %ds)", DUE_SOON_INTERVAL_SECONDS)
    while True:
        try:
            count = await _scan_due_soon_tasks()
            if count:
                logger.info("Created %d due-soon notifications", count)
        except Exception as e:
            logger.error("Notification worker error: %s", e)
        await asyncio.sleep(DUE_SOON_INTERVAL_SECONDS)
