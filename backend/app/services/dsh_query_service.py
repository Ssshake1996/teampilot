"""Bounded, read-only business data for DSH; analysis stays in the agent."""
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.services import task_service


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def page_result(items, total, page, page_size, scope):
    return {"items": items, "total": total, "page": page, "page_size": page_size,
        "has_more": page * page_size < total, "scope": scope,
        "queried_at": datetime.now(timezone.utc)}


async def query_tasks(db: AsyncSession, *, project_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None, status: TaskStatus | None = None, search: str = "",
    page: int = 1, page_size: int = 50):
    search = search.strip()
    filters = [Task.is_deleted == False, Project.status != ProjectStatus.ARCHIVED]
    if project_id is not None:
        filters.append(Task.project_id == project_id)
    if assignee_id is not None:
        filters.append(Task.id.in_(select(Assignment.task_id).where(
            Assignment.user_id == assignee_id, Assignment.kind == AssignmentKind.TASK_ASSIGNEE)))
    if status is not None:
        filters.append(task_service.effective_status_sql() == status.name)
    if search:
        filters.append(or_(*(field.icontains(search, autoescape=True)
            for field in (Task.title, Task.goal, Task.description))))

    total = (await db.execute(select(func.count(Task.id)).join(Project, Task.project_id == Project.id)
        .where(*filters))).scalar_one()
    rows = (await db.execute(select(Task, Project.name).join(Project, Task.project_id == Project.id)
        .where(*filters).order_by(Task.created_at.desc(), Task.id.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    tasks = [task for task, _name in rows]
    progress_map = {}
    if tasks:
        # Include every sibling/descendant in represented projects so a filtered page
        # preserves the existing weighted-parent progress calculation.
        project_ids = {task.project_id for task in tasks}
        project_tasks = (await db.execute(select(Task).where(Task.project_id.in_(project_ids)))).scalars().all()
        grouped_tasks = defaultdict(list)
        for task in project_tasks:
            grouped_tasks[task.project_id].append(task)
        ranked = select(Task.project_id, TaskEvent.task_id, TaskEvent.progress_pct,
            func.row_number().over(partition_by=TaskEvent.task_id,
                order_by=(TaskEvent.created_at.desc(), TaskEvent.id.desc())).label("rank"))\
            .join(Task, TaskEvent.task_id == Task.id).where(Task.project_id.in_(project_ids),
                TaskEvent.event_type == TaskEventType.PROGRESS, TaskEvent.progress_pct.isnot(None)).subquery()
        latest = defaultdict(dict)
        for row in (await db.execute(select(ranked).where(ranked.c.rank == 1))).all():
            latest[row.project_id][row.task_id] = row
        for pid, project_rows in grouped_tasks.items():
            progress_map.update(await task_service.get_project_task_progress_map(db, pid, project_rows, latest[pid]))
    assignees = await task_service.get_task_assignee_map(db, tasks)
    signers = await task_service.get_signer_names(db, tasks)
    items = [{**await task_service.task_to_out(db, task, assignee_map=assignees,
        progress_map=progress_map, signer_names=signers), "project_name": name} for task, name in rows]
    for item in items:
        for field in ("start_date", "deadline", "completed_at", "signed_off_at", "deleted_at", "created_at", "updated_at"):
            item[field] = utc(item[field])
    return page_result(items, total, page, page_size, {
        "project_id": str(project_id) if project_id else None,
        "assignee_id": str(assignee_id) if assignee_id else None,
        "status": status.value if status else None, "search": search, "timezone": "UTC",
        "include_archived": False, "include_deleted": False,
    })


async def query_progress(db: AsyncSession, *, project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None,
    since: datetime | None = None, until: datetime | None = None, page: int = 1, page_size: int = 50):
    since, until = utc(since), utc(until)
    if since is not None and until is not None and since >= until:
        raise HTTPException(422, "since must precede until (UTC; since inclusive, until exclusive)")
    filters = [TaskEvent.event_type == TaskEventType.PROGRESS,
        Task.is_deleted == False, Project.status != ProjectStatus.ARCHIVED]
    if project_id is not None:
        filters.append(Task.project_id == project_id)
    if task_id is not None:
        filters.append(TaskEvent.task_id == task_id)
    if user_id is not None:
        filters.append(TaskEvent.actor_id == user_id)
    if since is not None:
        filters.append(TaskEvent.created_at >= since)
    if until is not None:
        filters.append(TaskEvent.created_at < until)
    query = select(TaskEvent, Task.title, Task.project_id, Project.name, User.full_name)\
        .join(Task, TaskEvent.task_id == Task.id).join(Project, Task.project_id == Project.id)\
        .join(User, TaskEvent.actor_id == User.id).where(*filters)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    items = [{"id": event.id, "project_id": pid, "project_name": project_name,
        "task_id": event.task_id, "task_title": title, "user_id": event.actor_id,
        "user_name": user_name, "progress_pct": event.progress_pct, "note": event.note,
        "hours_spent": float(event.hours_spent) if event.hours_spent is not None else None,
        "created_at": utc(event.created_at)} for event, title, pid, project_name, user_name in rows]
    return page_result(items, total, page, page_size, {
        "project_id": str(project_id) if project_id else None,
        "task_id": str(task_id) if task_id else None, "user_id": str(user_id) if user_id else None,
        "user_filter": "progress_actor", "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None, "timezone": "UTC",
        "since_inclusive": True, "until_inclusive": False,
        "include_archived": False, "include_deleted": False,
    })
