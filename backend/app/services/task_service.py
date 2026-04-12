import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.task_progress import TaskProgress
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate


async def list_tasks(
    db: AsyncSession,
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    q = select(Task).where(Task.project_id == project_id)
    count_q = select(func.count(Task.id)).where(Task.project_id == project_id)

    if status:
        q = q.where(Task.status == status)
        count_q = count_q.where(Task.status == status)
    if assignee_id:
        q = q.where(Task.assignee_id == assignee_id)
        count_q = count_q.where(Task.assignee_id == assignee_id)

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(
        q.order_by(Task.sort_order, Task.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tasks = result.scalars().all()

    items = []
    for t in tasks:
        assignee_name = None
        if t.assignee_id:
            u = (await db.execute(select(User.full_name).where(User.id == t.assignee_id))).scalar()
            assignee_name = u

        # Get latest progress
        prog_q = await db.execute(
            select(TaskProgress.progress_pct)
            .where(TaskProgress.task_id == t.id)
            .order_by(TaskProgress.created_at.desc())
            .limit(1)
        )
        progress = prog_q.scalar() or 0
        if t.status == TaskStatus.DONE:
            progress = 100

        items.append({
            **{c.name: getattr(t, c.name) for c in t.__table__.columns},
            "assignee_name": assignee_name,
            "progress_pct": progress,
        })
    return items, total


async def create_task(
    db: AsyncSession, project_id: uuid.UUID, data: TaskCreate, creator_id: uuid.UUID
) -> Task:
    # Get max sort_order for the status column
    max_order_q = await db.execute(
        select(func.coalesce(func.max(Task.sort_order), 0)).where(
            Task.project_id == project_id, Task.status == data.status
        )
    )
    max_order = max_order_q.scalar()

    task = Task(
        **data.model_dump(),
        project_id=project_id,
        creator_id=creator_id,
        sort_order=max_order + 1,
    )
    db.add(task)
    await db.flush()
    return task


async def get_task(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def update_task(db: AsyncSession, task_id: uuid.UUID, data: TaskUpdate) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # If moving to done, set completed_at
    if update_data.get("status") == TaskStatus.DONE and task.status != TaskStatus.DONE:
        update_data["completed_at"] = datetime.now(timezone.utc)
    # If moving away from done, clear completed_at
    elif update_data.get("status") and update_data["status"] != TaskStatus.DONE:
        update_data["completed_at"] = None

    for field, value in update_data.items():
        setattr(task, field, value)
    await db.flush()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: uuid.UUID) -> bool:
    """Soft delete: mark as deleted, don't remove from DB."""
    task = await get_task(db, task_id)
    if not task:
        return False
    task.is_deleted = True
    task.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(task)
    return True


async def update_task_status(db: AsyncSession, task_id: uuid.UUID, status: TaskStatus) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None
    task.status = status
    if status == TaskStatus.DONE:
        task.completed_at = datetime.now(timezone.utc)
    else:
        task.completed_at = None
    await db.flush()
    await db.refresh(task)
    return task


async def assign_task(db: AsyncSession, task_id: uuid.UUID, assignee_id: uuid.UUID | None) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None
    task.assignee_id = assignee_id
    await db.flush()
    await db.refresh(task)
    return task


async def log_progress(
    db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID,
    progress_pct: int, note: str | None, hours_spent: float | None,
) -> TaskProgress:
    entry = TaskProgress(
        task_id=task_id,
        user_id=user_id,
        progress_pct=progress_pct,
        note=note,
        hours_spent=hours_spent,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_progress_history(db: AsyncSession, task_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(TaskProgress, User.full_name)
        .join(User, TaskProgress.user_id == User.id)
        .where(TaskProgress.task_id == task_id)
        .order_by(TaskProgress.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": tp.id, "task_id": tp.task_id, "user_id": tp.user_id,
            "user_name": name, "progress_pct": tp.progress_pct,
            "note": tp.note, "hours_spent": float(tp.hours_spent) if tp.hours_spent else None,
            "created_at": tp.created_at,
        }
        for tp, name in rows
    ]


async def reorder_tasks(db: AsyncSession, items: list[dict]) -> None:
    for item in items:
        await db.execute(
            update(Task)
            .where(Task.id == item["task_id"])
            .values(status=item["status"], sort_order=item["sort_order"])
        )
    await db.flush()


async def get_subtasks(db: AsyncSession, parent_task_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Task, User.full_name)
        .outerjoin(User, Task.assignee_id == User.id)
        .where(Task.parent_task_id == parent_task_id)
        .order_by(Task.sort_order, Task.created_at)
    )
    rows = result.all()
    items = []
    for t, assignee_name in rows:
        items.append({
            **{c.name: getattr(t, c.name) for c in t.__table__.columns},
            "assignee_name": assignee_name,
            "progress_pct": 100 if t.status == TaskStatus.DONE else 0,
        })
    return items
