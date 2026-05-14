import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
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


WEIGHT_TOTAL = Decimal("1.000000")
WEIGHT_SCALE = Decimal("0.000001")
WEIGHT_TOLERANCE = Decimal("0.01")
PERCENT_SCALE = Decimal("1")


def _decimal_weight(value: object, *, default: Decimal | None = None) -> Decimal:
    if value is None:
        if default is not None:
            return default
        raise ValueError("Task weight is required.")
    weight = Decimal(str(value)).quantize(WEIGHT_SCALE)
    if weight < 0 or weight > WEIGHT_TOTAL:
        raise ValueError("Task weight must be between 0 and 1.")
    return weight


def _split_weight_evenly(total: Decimal, count: int) -> list[Decimal]:
    if count <= 0:
        return []
    if count == 1:
        return [total]
    base = (total / Decimal(count)).quantize(WEIGHT_SCALE, rounding=ROUND_DOWN)
    weights = [base for _ in range(count)]
    weights[-1] = total - (base * Decimal(count - 1))
    return weights


async def _active_sibling_tasks(db: AsyncSession, parent_task_id: uuid.UUID) -> list[Task]:
    return (
        await db.execute(
            select(Task)
            .where(
                Task.parent_task_id == parent_task_id,
                Task.is_deleted == False,
            )
            .order_by(Task.sort_order, Task.created_at)
        )
    ).scalars().all()


async def rebalance_sibling_weights_evenly(
    db: AsyncSession,
    parent_task_id: uuid.UUID | None,
) -> None:
    if parent_task_id is None:
        return
    siblings = await _active_sibling_tasks(db, parent_task_id)
    for task, weight in zip(siblings, _split_weight_evenly(WEIGHT_TOTAL, len(siblings))):
        task.weight = weight
    await db.flush()


async def normalize_sibling_weights(
    db: AsyncSession,
    parent_task_id: uuid.UUID | None,
) -> None:
    if parent_task_id is None:
        return
    siblings = await _active_sibling_tasks(db, parent_task_id)
    if not siblings:
        return

    current_weights = [
        _decimal_weight(task.weight, default=WEIGHT_TOTAL) for task in siblings
    ]
    current_total = sum(current_weights, Decimal("0"))
    if current_total <= 0:
        for task, weight in zip(siblings, _split_weight_evenly(WEIGHT_TOTAL, len(siblings))):
            task.weight = weight
        await db.flush()
        return

    running = Decimal("0")
    for task, current in zip(siblings[:-1], current_weights[:-1]):
        next_weight = (current / current_total * WEIGHT_TOTAL).quantize(
            WEIGHT_SCALE,
            rounding=ROUND_DOWN,
        )
        task.weight = next_weight
        running += next_weight
    siblings[-1].weight = WEIGHT_TOTAL - running
    await db.flush()


async def set_sibling_weight(
    db: AsyncSession,
    task: Task,
    requested_weight: object,
) -> None:
    weight = _decimal_weight(requested_weight)
    if task.parent_task_id is None:
        task.weight = weight
        await db.flush()
        return

    siblings = await _active_sibling_tasks(db, task.parent_task_id)
    if len(siblings) <= 1:
        task.weight = WEIGHT_TOTAL
        await db.flush()
        return

    remaining = WEIGHT_TOTAL - weight
    other_tasks = [item for item in siblings if item.id != task.id]
    other_total = sum(
        (_decimal_weight(item.weight, default=WEIGHT_TOTAL) for item in other_tasks),
        Decimal("0"),
    )

    task.weight = weight
    if other_total <= 0:
        for other, other_weight in zip(other_tasks, _split_weight_evenly(remaining, len(other_tasks))):
            other.weight = other_weight
    else:
        running = Decimal("0")
        for other in other_tasks[:-1]:
            current = _decimal_weight(other.weight, default=WEIGHT_TOTAL)
            next_weight = (current / other_total * remaining).quantize(
                WEIGHT_SCALE,
                rounding=ROUND_DOWN,
            )
            other.weight = next_weight
            running += next_weight
        other_tasks[-1].weight = remaining - running

    total = sum(
        (_decimal_weight(item.weight, default=WEIGHT_TOTAL) for item in siblings),
        Decimal("0"),
    )
    if abs(total - WEIGHT_TOTAL) > WEIGHT_TOLERANCE:
        raise ValueError("Sibling task weights must sum to 1.")
    await db.flush()


def effective_task_status(task: Task, now: datetime | None = None) -> TaskStatus:
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


def normalize_assignee_ids(assignee_ids: list[uuid.UUID] | None = None) -> list[uuid.UUID]:
    normalized: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for item in assignee_ids or []:
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


async def get_project_task_progress_map(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.sort_order, Task.created_at)
        )
    ).scalars().all()
    if not tasks:
        return {}

    task_by_id = {task.id: task for task in tasks}
    children_by_parent: dict[uuid.UUID | None, list[Task]] = {}
    for task in tasks:
        children_by_parent.setdefault(task.parent_task_id, []).append(task)

    latest_progress: dict[uuid.UUID, int] = {}
    progress_rows = (
        await db.execute(
            select(TaskEvent.task_id, TaskEvent.progress_pct)
            .where(
                TaskEvent.task_id.in_(list(task_by_id.keys())),
                TaskEvent.event_type == TaskEventType.PROGRESS,
                TaskEvent.progress_pct.isnot(None),
            )
            .order_by(TaskEvent.created_at.desc())
        )
    ).all()
    for task_id, progress_pct in progress_rows:
        latest_progress.setdefault(task_id, progress_pct)

    progress_cache: dict[uuid.UUID, int] = {}
    visiting: set[uuid.UUID] = set()

    def compute(task_id: uuid.UUID) -> int:
        if task_id in progress_cache:
            return progress_cache[task_id]
        task = task_by_id.get(task_id)
        if task is None:
            return 0
        if task_id in visiting:
            return latest_progress.get(task_id, 0)

        visiting.add(task_id)
        active_children = [
            child for child in children_by_parent.get(task_id, [])
            if not child.is_deleted
        ]
        if task.status == TaskStatus.DONE:
            progress = 100
        elif active_children:
            weighted_sum = Decimal("0")
            weight_sum = Decimal("0")
            for child in active_children:
                child_progress = Decimal(compute(child.id))
                child_weight = _decimal_weight(child.weight, default=WEIGHT_TOTAL)
                weighted_sum += child_progress * child_weight
                weight_sum += child_weight

            if weight_sum <= 0:
                progress = round(sum(compute(child.id) for child in active_children) / len(active_children))
            else:
                progress = int(
                    (weighted_sum / weight_sum).quantize(PERCENT_SCALE, rounding=ROUND_HALF_UP)
                )
        else:
            progress = latest_progress.get(task_id, 0)

        visiting.remove(task_id)
        progress_cache[task_id] = max(0, min(100, progress))
        return progress_cache[task_id]

    return {task.id: compute(task.id) for task in tasks}


async def get_task_progress_pct(db: AsyncSession, task: Task) -> int:
    progress_map = await get_project_task_progress_map(db, task.project_id)
    return progress_map.get(task.id, 0)


async def get_task_assignee_map(
    db: AsyncSession,
    tasks: list[Task],
) -> dict[uuid.UUID, list[dict]]:
    task_ids = [task.id for task in tasks]
    if not task_ids:
        return {}

    rows = (
        await db.execute(
            select(Assignment.task_id, Assignment.user_id, User.full_name)
            .join(User, Assignment.user_id == User.id)
            .where(
                Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
                Assignment.task_id.in_(task_ids),
            )
        )
    ).all()
    mapping: dict[uuid.UUID, list[dict]] = {task_id: [] for task_id in task_ids}
    for task_id, user_id, full_name in rows:
        mapping.setdefault(task_id, []).append({
            "user_id": user_id,
            "full_name": full_name,
        })

    for assignees in mapping.values():
        assignees.sort(key=lambda item: ((item["full_name"] or ""), str(item["user_id"])))
    return mapping


async def sync_task_assignees(
    db: AsyncSession,
    task: Task,
    assignee_ids: list[uuid.UUID],
) -> None:
    normalized = normalize_assignee_ids(assignee_ids)
    existing_rows = (
        await db.execute(
            select(Assignment).where(
                Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
                Assignment.task_id == task.id,
            )
        )
    ).scalars().all()
    existing_ids = {row.user_id for row in existing_rows}
    desired_ids = set(normalized)

    for row in existing_rows:
        if row.user_id not in desired_ids:
            await db.delete(row)

    for user_id in normalized:
        if user_id not in existing_ids:
            db.add(Assignment(
                project_id=task.project_id,
                task_id=task.id,
                user_id=user_id,
                kind=AssignmentKind.TASK_ASSIGNEE,
                role="assignee",
            ))

    await db.flush()


async def task_to_out(
    db: AsyncSession,
    task: Task,
    assignee_name: str | None = None,
    assignee_map: dict[uuid.UUID, list[dict]] | None = None,
    progress_map: dict[uuid.UUID, int] | None = None,
) -> dict:
    assignees = (assignee_map or {}).get(task.id)
    if assignees is None:
        assignees = (await get_task_assignee_map(db, [task])).get(task.id, [])
    assignee_ids = [item["user_id"] for item in assignees]
    assignee_names = [item["full_name"] for item in assignees if item["full_name"]]
    if assignee_name is None and assignee_names:
        assignee_name = ", ".join(assignee_names)

    signed_off_by_name = None
    if task.signed_off_by_id:
        signed_off_by_name = (
            await db.execute(select(User.full_name).where(User.id == task.signed_off_by_id))
        ).scalar()

    return {
        **{c.name: getattr(task, c.name) for c in task.__table__.columns},
        "status": effective_task_status(task),
        "assignee_name": assignee_name,
        "assignee_ids": assignee_ids,
        "assignee_names": assignee_names,
        "signed_off_by_name": signed_off_by_name,
        "weight": float(_decimal_weight(task.weight, default=WEIGHT_TOTAL)),
        "progress_pct": (
            progress_map.get(task.id, 0)
            if progress_map is not None
            else await get_task_progress_pct(db, task)
        ),
    }


async def list_tasks(
    db: AsyncSession,
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    user_id: uuid.UUID | None = None,
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

    if user_id:
        assigned_task_ids = select(Assignment.task_id).where(
            Assignment.user_id == user_id,
            Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
        )
        q = q.where(Task.id.in_(assigned_task_ids))
        count_q = count_q.where(Task.id.in_(assigned_task_ids))

    total = (await db.execute(count_q)).scalar()
    tasks = (
        await db.execute(
            q.order_by(Task.sort_order, Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    assignee_map = await get_task_assignee_map(db, tasks)
    progress_map = await get_project_task_progress_map(db, project_id) if tasks else {}
    items = [
        await task_to_out(db, task, assignee_map=assignee_map, progress_map=progress_map)
        for task in tasks
    ]
    return items, total


async def create_task(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: TaskCreate,
    creator_id: uuid.UUID,
) -> Task:
    task_data = data.model_dump()
    assignee_ids = normalize_assignee_ids(task_data.pop("assignee_ids", None))
    requested_weight = task_data.pop("weight", None)
    if task_data.get("status") is None:
        task_data["status"] = initial_task_status(data.start_date)
    if requested_weight is not None:
        task_data["weight"] = _decimal_weight(requested_weight)

    max_order = (
        await db.execute(
            select(func.coalesce(func.max(Task.sort_order), 0)).where(
                Task.project_id == project_id,
                Task.status == task_data["status"],
            )
        )
    ).scalar()

    task = Task(
        **task_data,
        project_id=project_id,
        creator_id=creator_id,
        sort_order=max_order + 1,
    )
    db.add(task)
    await db.flush()
    await sync_task_assignees(db, task, assignee_ids)
    if task.parent_task_id:
        if requested_weight is None:
            await rebalance_sibling_weights_evenly(db, task.parent_task_id)
        else:
            await set_sibling_weight(db, task, requested_weight)
    return task


async def get_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    include_deleted: bool = False,
) -> Task | None:
    query = select(Task).where(Task.id == task_id)
    if not include_deleted:
        query = query.where(Task.is_deleted == False)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_task_descendants(db: AsyncSession, task: Task) -> list[Task]:
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.project_id == task.project_id)
            .order_by(Task.created_at)
        )
    ).scalars().all()

    children_by_parent: dict[uuid.UUID | None, list[Task]] = {}
    for item in tasks:
        children_by_parent.setdefault(item.parent_task_id, []).append(item)

    descendants: list[Task] = []
    stack = list(children_by_parent.get(task.id, []))
    while stack:
        current = stack.pop()
        descendants.append(current)
        stack.extend(children_by_parent.get(current.id, []))
    return descendants


async def update_task(db: AsyncSession, task_id: uuid.UUID, data: TaskUpdate) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data:
        raise ValueError("Task status is automatic. Submit progress and sign off completed tasks.")

    assignee_ids = normalize_assignee_ids(update_data.pop("assignee_ids", None)) if "assignee_ids" in update_data else None
    has_weight_update = "weight" in update_data
    requested_weight = update_data.pop("weight", None) if has_weight_update else None
    if has_weight_update and requested_weight is None:
        raise ValueError("Task weight is required.")

    for field, value in update_data.items():
        setattr(task, field, value)
    if assignee_ids is not None:
        await sync_task_assignees(db, task, assignee_ids)
    if has_weight_update:
        await set_sibling_weight(db, task, requested_weight)
    await db.flush()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> bool:
    task = await get_task(db, task_id, include_deleted=True)
    if not task:
        return False
    deleted_at = _now()
    affected_parent_ids: set[uuid.UUID] = set()
    for item in [task, *await get_task_descendants(db, task)]:
        if item.parent_task_id:
            affected_parent_ids.add(item.parent_task_id)
        item.is_deleted = True
        item.deleted_at = deleted_at
        if actor_id:
            db.add(TaskEvent(
                task_id=item.id,
                actor_id=actor_id,
                event_type=TaskEventType.DELETE,
                note="Task deleted",
            ))
    for parent_task_id in affected_parent_ids:
        await normalize_sibling_weights(db, parent_task_id)
    await db.flush()
    await db.refresh(task)
    return True


async def restore_task(db: AsyncSession, task_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Task | None:
    task = await get_task(db, task_id, include_deleted=True)
    if not task:
        return None

    if task.parent_task_id:
        parent = await get_task(db, task.parent_task_id, include_deleted=True)
        if parent and parent.is_deleted:
            raise ValueError("Parent task is deleted. Restore the parent task first.")

    affected_parent_ids: set[uuid.UUID] = set()
    for item in [task, *await get_task_descendants(db, task)]:
        if item.parent_task_id:
            affected_parent_ids.add(item.parent_task_id)
        item.is_deleted = False
        item.deleted_at = None
        if actor_id:
            db.add(TaskEvent(
                task_id=item.id,
                actor_id=actor_id,
                event_type=TaskEventType.RESTORE,
                note="Task restored",
            ))
    for parent_task_id in affected_parent_ids:
        await normalize_sibling_weights(db, parent_task_id)
    await db.flush()
    await db.refresh(task)
    return task


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
    db.add(TaskEvent(
        task_id=task.id,
        actor_id=user_id,
        event_type=TaskEventType.SIGNOFF,
        progress_pct=100,
        note="Task signed off",
    ))
    await db.flush()
    await db.refresh(task)
    return task


async def assign_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    assignee_ids: list[uuid.UUID],
) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        return None
    await sync_task_assignees(db, task, normalize_assignee_ids(assignee_ids))
    await db.refresh(task)
    return task


async def log_progress(
    db: AsyncSession,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    progress_pct: int,
    note: str | None,
    hours_spent: float | None,
) -> TaskEvent:
    if progress_pct < 0 or progress_pct > 100:
        raise ValueError("Progress must be between 0 and 100.")

    task = await get_task(db, task_id, include_deleted=True)
    if not task:
        raise ValueError("Task not found.")
    if task.is_deleted:
        raise ValueError("Deleted tasks cannot accept progress updates.")

    entry = TaskEvent(
        task_id=task_id,
        actor_id=user_id,
        event_type=TaskEventType.PROGRESS,
        progress_pct=progress_pct,
        note=note,
        hours_spent=hours_spent,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_progress_history(db: AsyncSession, task_id: uuid.UUID) -> list[dict]:
    rows = (
        await db.execute(
            select(TaskEvent, User.full_name)
            .join(User, TaskEvent.actor_id == User.id)
            .where(
                TaskEvent.task_id == task_id,
                TaskEvent.event_type == TaskEventType.PROGRESS,
            )
            .order_by(TaskEvent.created_at.desc())
        )
    ).all()
    return [
        {
            "id": tp.id,
            "task_id": tp.task_id,
            "user_id": tp.actor_id,
            "user_name": name,
            "progress_pct": tp.progress_pct,
            "note": tp.note,
            "hours_spent": float(tp.hours_spent) if tp.hours_spent else None,
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
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.parent_task_id == parent_task_id)
            .order_by(Task.sort_order, Task.created_at)
        )
    ).scalars().all()
    assignee_map = await get_task_assignee_map(db, tasks)
    progress_map = await get_project_task_progress_map(db, tasks[0].project_id) if tasks else {}
    return [
        await task_to_out(db, task, assignee_map=assignee_map, progress_map=progress_map)
        for task in tasks
    ]
