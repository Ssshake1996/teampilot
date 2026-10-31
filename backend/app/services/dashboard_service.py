import uuid
from datetime import datetime

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.services.task_service import effective_task_status, effective_status_sql


# Only count tasks from non-archived projects
_active_task = (
    select(Task.id)
    .join(Project, Task.project_id == Project.id)
    .where(Project.status != ProjectStatus.ARCHIVED)
).correlate(Task)


async def get_overview(db: AsyncSession) -> dict:
    now = datetime.utcnow()

    base = select(func.count(Task.id)).join(Project, Task.project_id == Project.id).where(Project.status != ProjectStatus.ARCHIVED, Task.is_deleted == False)
    total = (await db.execute(base)).scalar()
    in_progress = (await db.execute(base.where(effective_status_sql(now) == TaskStatus.IN_PROGRESS.name))).scalar()
    overdue = (await db.execute(base.where(Task.status != TaskStatus.DONE, Task.deadline < now))).scalar()
    done = (await db.execute(base.where(Task.status == TaskStatus.DONE))).scalar()
    rate = round((done / total * 100) if total > 0 else 0, 1)

    return {
        "total_tasks": total,
        "in_progress_tasks": in_progress,
        "overdue_tasks": overdue,
        "completion_rate": rate,
    }


async def get_team_workload(db: AsyncSession) -> list[dict]:
    now = datetime.utcnow()
    users = (
        await db.execute(
            select(User)
            .where(User.is_active == True)
            .order_by(User.full_name)
        )
    ).scalars().all()

    task_parents = (
        await db.execute(
            select(Task.id, Task.parent_task_id)
            .join(Project, Task.project_id == Project.id)
            .where(Project.status != ProjectStatus.ARCHIVED, Task.is_deleted == False)
        )
    ).all()
    parent_by_id: dict[uuid.UUID, uuid.UUID | None] = {
        task_id: parent_id for task_id, parent_id in task_parents
    }

    def task_depth(task_id: uuid.UUID) -> int:
        depth = 0
        current = parent_by_id.get(task_id)
        seen: set[uuid.UUID] = set()
        while current and current not in seen:
            seen.add(current)
            depth += 1
            current = parent_by_id.get(current)
        return depth

    def fallback_workload_hours(depth: int) -> float:
        if depth <= 0:
            return 8.0
        if depth == 1:
            return 4.0
        return 2.0

    def task_workload_hours(task: Task) -> float:
        if task.estimated_hours is not None:
            estimated = float(task.estimated_hours)
            if estimated > 0:
                return estimated
        return fallback_workload_hours(task_depth(task.id))

    result_by_user = {
        user.id: {
            "user_id": user.id,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "assigned_tasks": 0,
            "in_progress_tasks": 0,
            "completed_tasks": 0,
            "overdue_tasks": 0,
            "workload_hours": 0.0,
            "fallback_task_count": 0,
            "fallback_hours": 0.0,
        }
        for user in users
    }

    rows = (
        await db.execute(
            select(Assignment.user_id, Task)
            .join(Task, Assignment.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .where(
                Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
                Project.status != ProjectStatus.ARCHIVED,
                Task.is_deleted == False,
            )
        )
    ).all()

    seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for user_id, task in rows:
        if user_id not in result_by_user:
            continue
        pair = (user_id, task.id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        item = result_by_user[user_id]
        status = effective_task_status(task)
        if status == TaskStatus.DONE:
            item["completed_tasks"] += 1
            continue

        item["assigned_tasks"] += 1
        hours = task_workload_hours(task)
        item["workload_hours"] += hours
        if task.estimated_hours is None or float(task.estimated_hours) <= 0:
            item["fallback_task_count"] += 1
            item["fallback_hours"] += hours
        if status == TaskStatus.IN_PROGRESS:
            item["in_progress_tasks"] += 1
        if task.deadline and task.deadline.replace(tzinfo=None) < now:
            item["overdue_tasks"] += 1

    for item in result_by_user.values():
        item["workload_hours"] = round(item["workload_hours"], 1)
        item["fallback_hours"] = round(item["fallback_hours"], 1)

    return list(result_by_user.values())


async def get_recent_activity(db: AsyncSession, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(TaskEvent, User.full_name, Task.title, Project.name, Task.project_id)
        .join(User, TaskEvent.actor_id == User.id)
        .join(Task, TaskEvent.task_id == Task.id)
        .join(Project, Task.project_id == Project.id)
        .where(
            Project.status != ProjectStatus.ARCHIVED,
            Task.is_deleted == False,
            TaskEvent.event_type == TaskEventType.PROGRESS,
        )
        .order_by(TaskEvent.created_at.desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "id": tp.id, "task_id": tp.task_id, "project_id": project_id,
            "user_name": uname, "task_title": ttitle,
            "project_name": pname, "progress_pct": tp.progress_pct,
            "note": tp.note, "created_at": tp.created_at,
        }
        for tp, uname, ttitle, pname, project_id in rows
    ]


async def get_my_tasks_quadrant(db: AsyncSession, user_id) -> dict:
    """Get user's undone tasks grouped into 4 quadrants:
    - urgent_important: high/urgent priority, deadline within 3 days or overdue
    - important_not_urgent: high/urgent priority, deadline > 3 days
    - urgent_not_important: medium/low priority, deadline within 3 days or overdue
    - not_urgent_not_important: medium/low priority, deadline > 3 days or no deadline
    """
    import uuid as uuid_mod
    now = datetime.utcnow()
    from datetime import timedelta
    soon = now + timedelta(days=3)

    result = await db.execute(
        select(Task, Project.name)
        .join(Project, Task.project_id == Project.id)
        .where(
            Task.id.in_(select(Assignment.task_id).where(
                Assignment.user_id == (
                    user_id if isinstance(user_id, uuid_mod.UUID) else uuid_mod.UUID(str(user_id))
                ),
                Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
            )),
            Task.status != TaskStatus.DONE,
            Task.is_deleted == False,
            Project.status != ProjectStatus.ARCHIVED,
        )
        .order_by(Task.deadline.asc().nullslast())
    )
    rows = result.all()

    quadrants = {
        "urgent_important": [],
        "important_not_urgent": [],
        "urgent_not_important": [],
        "not_urgent_not_important": [],
    }

    for t, pname in rows:
        is_high = t.priority.value in ("high", "urgent")
        dl = t.deadline.replace(tzinfo=None) if t.deadline else None
        is_soon = dl is not None and dl <= soon

        item = {
            "id": str(t.id), "title": t.title, "status": effective_task_status(t).value,
            "priority": t.priority.value, "project_name": pname,
            "project_id": str(t.project_id),
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "is_overdue": bool(dl and dl < now),
            "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
        }

        if is_high and is_soon:
            quadrants["urgent_important"].append(item)
        elif is_high and not is_soon:
            quadrants["important_not_urgent"].append(item)
        elif not is_high and is_soon:
            quadrants["urgent_not_important"].append(item)
        else:
            quadrants["not_urgent_not_important"].append(item)

    return quadrants


async def get_project_progress(db: AsyncSession) -> list[dict]:
    """Get all active projects with task completion stats."""
    result = await db.execute(
        select(Project).where(Project.status != ProjectStatus.ARCHIVED).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    stats = (await db.execute(select(
        Task.project_id, func.count(Task.id),
        func.sum(case((Task.status == TaskStatus.DONE, 1), else_=0)),
        func.sum(case((effective_status_sql() == TaskStatus.IN_PROGRESS.name, 1), else_=0)),
        func.sum(case(((Task.status != TaskStatus.DONE) & (Task.deadline < datetime.utcnow()), 1), else_=0)),
    ).where(Task.is_deleted == False).group_by(Task.project_id))).all()
    stats_by_id = {pid: values for pid, *values in stats}

    items = []
    for p in projects:
        total, done, in_prog, overdue = stats_by_id.get(p.id, (0, 0, 0, 0))
        status = ProjectStatus.PLANNING if not total or (done == 0 and in_prog == 0) else (
            ProjectStatus.COMPLETED if done == total else ProjectStatus.ACTIVE
        )

        items.append({
            "id": str(p.id), "name": p.name, "status": status.value,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "total_tasks": total, "done_tasks": done, "in_progress_tasks": in_prog,
            "overdue_tasks": overdue,
            "progress_pct": round(done / total * 100) if total > 0 else 0,
        })
    return items
