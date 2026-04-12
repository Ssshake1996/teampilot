from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_progress import TaskProgress
from app.models.user import User


# Only count tasks from non-archived projects
_active_task = (
    select(Task.id)
    .join(Project, Task.project_id == Project.id)
    .where(Project.status != ProjectStatus.ARCHIVED)
).correlate(Task)


async def get_overview(db: AsyncSession) -> dict:
    now = datetime.utcnow()

    base = select(func.count(Task.id)).join(Project, Task.project_id == Project.id).where(Project.status != ProjectStatus.ARCHIVED)
    total = (await db.execute(base)).scalar()
    in_progress = (await db.execute(base.where(Task.status == TaskStatus.IN_PROGRESS))).scalar()
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
    users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()

    result = []
    for u in users:
        base_q = select(func.count(Task.id)).join(Project, Task.project_id == Project.id).where(
            Task.assignee_id == u.id, Project.status != ProjectStatus.ARCHIVED
        )
        assigned = (await db.execute(base_q.where(Task.status != TaskStatus.DONE))).scalar()
        in_prog = (await db.execute(base_q.where(Task.status == TaskStatus.IN_PROGRESS))).scalar()
        completed = (await db.execute(base_q.where(Task.status == TaskStatus.DONE))).scalar()
        overdue = (await db.execute(base_q.where(Task.status != TaskStatus.DONE, Task.deadline < now))).scalar()
        result.append({
            "user_id": u.id, "full_name": u.full_name, "avatar_url": u.avatar_url,
            "assigned_tasks": assigned, "in_progress_tasks": in_prog,
            "completed_tasks": completed, "overdue_tasks": overdue,
        })
    return result


async def get_recent_activity(db: AsyncSession, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(TaskProgress, User.full_name, Task.title, Project.name)
        .join(User, TaskProgress.user_id == User.id)
        .join(Task, TaskProgress.task_id == Task.id)
        .join(Project, Task.project_id == Project.id)
        .where(Project.status != ProjectStatus.ARCHIVED)
        .order_by(TaskProgress.created_at.desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "id": tp.id, "user_name": uname, "task_title": ttitle,
            "project_name": pname, "progress_pct": tp.progress_pct,
            "note": tp.note, "created_at": tp.created_at,
        }
        for tp, uname, ttitle, pname in rows
    ]
