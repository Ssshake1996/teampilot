import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.task_progress import TaskProgress
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def effective_task_status(task: Task, now: datetime | None = None) -> TaskStatus:
    """Return the business status shown to users."""
    if task.status == TaskStatus.DONE:
        return TaskStatus.DONE

    current = now or _now()
    start_date = _aware(task.start_date)
    if start_date and start_date > current:
        return TaskStatus.NOT_STARTED
    return TaskStatus.IN_PROGRESS


def initial_task_status(start_date: datetime | None) -> TaskStatus:
    start = _aware(start_date)
    if start and start > _now():
        return TaskStatus.NOT_STARTED
    return TaskStatus.IN_PROGRESS


async def get_task_progress_pct(db: AsyncSession, task: Task) -> int:
    if task.status == TaskStatus.DONE:
        return 100

    child_total = (await db.execute(
        select(func.count(Task.id)).where(
            Task.parent_task_id == task.id,
            Task.is_deleted == False,
        )
    )).scalar() or 0
    if child_total:
        child_done = (await db.execute(
            select(func.count(Task.id)).where(
                Task.parent_task_id == task.id,
                Task.status == TaskStatus.DONE,
                Task.is_deleted == False,
            )
        )).scalar() or 0
        return round(child_done / child_total * 100)

    progress = (await db.execute(
        select(TaskProgress.progress_pct)
        .where(TaskProgress.task_id == task.id)
        .order_by(TaskProgress.created_at.desc())
        .limit(1)
    )).scalar()
    return progress or 0


async def task_to_out(db: AsyncSession, task: Task, assignee_name: str | None = None) -> dict:
    if assignee_name is None and task.assignee_id:
        assignee_name = (await db.execute(
            select(User.full_name).where(User.id == task.assignee_id)
        )).scalar()

    signed_off_by_name = None
    if task.signed_off_by_id:
        signed_off_by_name = (await db.execute(
            select(User.full_name).where(User.id == task.signed_off_by_id)
        )).scalar()

    return {
        **{c.name: getattr(task, c.name) for c in task.__table__.columns},
        "status": effective_task_status(task),
        "assignee_name": assignee_name,
        "signed_off_by_name": signed_off_by_name,
        "progress_pct": await get_task_progress_pct(db, task),
    }


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

    if status == TaskStatus.DONE:
        q = q.where(Task.status == TaskStatus.DONE)
        count_q = count_q.where(Task.status == TaskStatus.DONE)
    elif status == TaskStatus.NOT_STARTED:
        now = _now()
        q = q.where(Task.status != TaskStatus.DONE, Task.start_date.isnot(None), Task.start_date > now)
        count_q = count_q.where(Task.status != TaskStatus.DONE, Task.start_date.isnot(None), Task.start_date > now)
    elif status == TaskStatus.IN_PROGRESS:
        now = _now()
        q = q.where(Task.status != TaskStatus.DONE).where(
            (Task.start_date.is_(None)) | (Task.start_date <= now)
        )
        count_q = count_q.where(Task.status != TaskStatus.DONE).where(
            (Task.start_date.is_(None)) | (Task.start_date <= now)
        )
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

        items.append(await task_to_out(db, t, assignee_name))
    return items, total


async def create_task(
    db: AsyncSession, project_id: uuid.UUID, data: TaskCreate, creator_id: uuid.UUID
) -> Task:
    task_data = data.model_dump()
    if task_data.get("status") is None:
        task_data["status"] = initial_task_status(data.start_date)

    # Get max sort_order for the status column
    max_order_q = await db.execute(
        select(func.coalesce(func.max(Task.sort_order), 0)).where(
            Task.project_id == project_id, Task.status == task_data["status"]
        )
    )
    max_order = max_order_q.scalar()

    task = Task(
        **task_data,
        project_id=project_id,
        creator_id=creator_id,
        sort_order=max_order + 1,
    )
    db.add(task)
    await db.flush()
    return task


async def get_task(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.is_deleted == False))
    return result.scalar_one_or_none()


async def update_task(db: AsyncSession, task_id: uuid.UUID, data: TaskUpdate) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data:
        raise ValueError("Task status is automatic. Submit progress and sign off completed tasks.")

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
    raise ValueError("Task status is automatic. Submit progress and sign off completed tasks.")


async def signoff_task(db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None

    progress = await get_task_progress_pct(db, task)
    if progress < 100:
        raise ValueError("Task progress must be 100% before signoff.")

    signed_at = _now()
    task.status = TaskStatus.DONE
    task.completed_at = signed_at
    task.signed_off_by_id = user_id
    task.signed_off_at = signed_at
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
    if progress_pct < 0 or progress_pct > 100:
        raise ValueError("Progress must be between 0 and 100.")

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
            .values(sort_order=item["sort_order"])
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
        items.append(await task_to_out(db, t, assignee_name))
    return items
