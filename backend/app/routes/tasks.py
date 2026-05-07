from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_scope
from app.database import get_db
from app.models import Task, User, UserRole
from app.routes.notifications import add_notification
from app.schemas import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=dict)
async def list_tasks(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str = Query(""),
    contact_id: UUID | None = Query(None),
    deal_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("tasks:read")),
):
    query = select(Task)
    if current_user.role == UserRole.USER:
        query = query.where(Task.assigned_to == current_user.id)
    if status:
        query = query.where(Task.status == status)
    if contact_id:
        query = query.where(Task.contact_id == contact_id)
    if deal_id:
        query = query.where(Task.deal_id == deal_id)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    query = query.order_by(Task.due_date.asc().nullslast()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "items": [TaskRead.model_validate(t) for t in items],
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.post("", response_model=TaskRead)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("tasks:write"))):
    task = Task(**data.model_dump())
    if task.assigned_to is None:
        task.assigned_to = current_user.id
    db.add(task)
    await db.flush()
    if task.assigned_to and task.assigned_to != current_user.id:
        add_notification(
            db,
            user_id=task.assigned_to,
            title=f"Task assigned: {task.title}",
            message=f"{current_user.full_name or current_user.email} assigned you a task.",
            entity_type="task",
            entity_id=task.id,
        )
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: UUID, data: TaskUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("tasks:write"))):
    query = select(Task).where(Task.id == task_id)
    if current_user.role == UserRole.USER:
        query = query.where(Task.assigned_to == current_user.id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    old_assigned_to = task.assigned_to
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    if (
        task.assigned_to
        and task.assigned_to != old_assigned_to
        and task.assigned_to != current_user.id
    ):
        add_notification(
            db,
            user_id=task.assigned_to,
            title=f"Task assigned: {task.title}",
            message=f"{current_user.full_name or current_user.email} assigned you a task.",
            entity_type="task",
            entity_id=task.id,
        )
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_scope("tasks:write"))):
    query = select(Task).where(Task.id == task_id)
    if current_user.role == UserRole.USER:
        query = query.where(Task.assigned_to == current_user.id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await db.commit()
    return {"ok": True}
