import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import async_session
from app.models import Notification, Task, TaskStatus

logger = logging.getLogger(__name__)

DUE_SOON_INTERVAL_SECONDS = 900  # 15 minutes
DEFAULT_REMINDER_WINDOW_MINUTES = 24 * 60  # tasks without explicit reminder use 24h
DUE_SOON_TITLE_PREFIX = "Task due soon"


async def _scan_due_soon_tasks() -> int:
    """Find tasks whose reminder window opens soon and create one notification each."""
    now = datetime.now(timezone.utc)
    # We pull a generous window and decide per-task using its reminder_minutes_before.
    max_lead = timedelta(minutes=DEFAULT_REMINDER_WINDOW_MINUTES)

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
            Task.due_date <= now + max_lead,
            Task.due_date > now,
            ~notif_exists,
        )
        candidates = (await db.execute(query)).scalars().all()
        created = 0
        for task in candidates:
            lead_minutes = task.reminder_minutes_before or DEFAULT_REMINDER_WINDOW_MINUTES
            if task.due_date - now > timedelta(minutes=lead_minutes):
                continue
            db.add(
                Notification(
                    user_id=task.assigned_to,
                    title=f"{DUE_SOON_TITLE_PREFIX}: {task.title}",
                    message=f"This task is due {task.due_date.isoformat()}.",
                    entity_type="task",
                    entity_id=task.id,
                )
            )
            created += 1
        if created:
            await db.commit()
        return created


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
