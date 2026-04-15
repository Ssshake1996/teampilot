import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, delete, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMember, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.task_service import effective_task_status


async def list_projects(db: AsyncSession, page: int = 1, page_size: int = 20, include_archived: bool = False) -> tuple[list[dict], int]:
    base_filter = [] if include_archived else [Project.status != ProjectStatus.ARCHIVED]

    total_q = await db.execute(select(func.count(Project.id)).where(*base_filter))
    total = total_q.scalar()

    result = await db.execute(
        select(Project).where(*base_filter).order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    projects = result.scalars().all()

    items = []
    for p in projects:
        task_count_q = await db.execute(select(func.count(Task.id)).where(Task.project_id == p.id, Task.is_deleted == False))
        task_count = task_count_q.scalar()
        done_count_q = await db.execute(
            select(func.count(Task.id)).where(Task.project_id == p.id, Task.status == TaskStatus.DONE, Task.is_deleted == False)
        )
        done_count = done_count_q.scalar()
        member_count_q = await db.execute(
            select(func.count(ProjectMember.user_id)).where(ProjectMember.project_id == p.id)
        )
        member_count = member_count_q.scalar()

        items.append({
            "id": p.id, "name": p.name, "description": p.description,
            "status": p.status, "owner_id": p.owner_id,
            "start_date": p.start_date, "end_date": p.end_date,
            "created_at": p.created_at,
            "task_count": task_count, "completed_count": done_count,
            "member_count": member_count,
        })
    return items, total


async def create_project(db: AsyncSession, data: ProjectCreate, owner_id: uuid.UUID) -> Project:
    project = Project(**data.model_dump(), owner_id=owner_id)
    db.add(project)
    await db.flush()
    # Add owner as lead member
    db.add(ProjectMember(project_id=project.id, user_id=owner_id, role_in_project="lead"))
    await db.flush()
    return project


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def update_project(db: AsyncSession, project_id: uuid.UUID, data: ProjectUpdate) -> Project | None:
    project = await get_project(db, project_id)
    if not project:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.flush()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: uuid.UUID) -> bool:
    project = await get_project(db, project_id)
    if not project:
        return False
    project.status = ProjectStatus.ARCHIVED
    await db.flush()
    return True


async def get_project_members(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
    )
    rows = result.all()
    return [
        {"user_id": pm.user_id, "full_name": u.full_name, "role_in_project": pm.role_in_project}
        for pm, u in rows
    ]


async def add_project_member(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> None:
    db.add(ProjectMember(project_id=project_id, user_id=user_id, role_in_project=role))
    await db.flush()


async def remove_project_member(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await db.execute(
        delete(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    )
    await db.flush()


async def get_project_task_tree(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    """Get parent tasks with subtask children, assignee info, and progress."""
    now = datetime.utcnow()  # naive UTC for SQLite compatibility

    # All tasks for this project, joined with assignee
    result = await db.execute(
        select(Task, User.full_name)
        .outerjoin(User, Task.assignee_id == User.id)
        .where(Task.project_id == project_id)
        .order_by(Task.sort_order, Task.created_at)
    )
    rows = result.all()

    # Build lookup: task_id -> task dict, and parent_id -> children list
    all_tasks = {}
    children_map: dict[str, list] = {}
    for t, assignee_name in rows:
        status = effective_task_status(t).value
        td = {
            "id": str(t.id),
            "title": t.title,
            "status": status,
            "priority": t.priority.value,
            "assignee_id": str(t.assignee_id) if t.assignee_id else None,
            "assignee_name": assignee_name,
            "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
            "actual_hours": float(t.actual_hours) if t.actual_hours else None,
            "start_date": (t.start_date or t.created_at).isoformat() if (t.start_date or t.created_at) else None,
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "signed_off_by_id": str(t.signed_off_by_id) if t.signed_off_by_id else None,
            "signed_off_at": t.signed_off_at.isoformat() if t.signed_off_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
            "is_deleted": bool(t.is_deleted),
            "is_overdue": bool(not t.is_deleted and t.deadline and t.deadline.replace(tzinfo=None) < now and status != "done"),
            "children": [],
        }
        all_tasks[str(t.id)] = td
        if t.parent_task_id:
            pid = str(t.parent_task_id)
            children_map.setdefault(pid, []).append(td)

    # Get latest progress_pct per task from task_progress table
    from app.models.task_progress import TaskProgress
    progress_map: dict[str, int] = {}
    note_map: dict[str, str] = {}
    prog_result = await db.execute(
        select(TaskProgress.task_id, TaskProgress.progress_pct, TaskProgress.note)
        .join(Task, TaskProgress.task_id == Task.id)
        .where(Task.project_id == project_id)
        .order_by(TaskProgress.created_at.desc())
    )
    for tid_raw, pct, note in prog_result.all():
        tid_str = str(tid_raw)
        if tid_str not in progress_map:
            progress_map[tid_str] = pct
            note_map[tid_str] = note or ""

    # Assemble tree: attach children, compute progress
    roots = []
    for tid, td in all_tasks.items():
        td["children"] = children_map.get(tid, [])
        children = td["children"]

        if children:
            active_children = [c for c in children if not c.get("is_deleted")]
            done_children = sum(1 for c in active_children if c["status"] == "done")
            total_active = len(active_children) or 1
            td["progress_pct"] = round(done_children / total_active * 100)
            td["subtask_total"] = len(active_children)
            td["subtask_done"] = done_children
        else:
            # Leaf task: use logged progress, or 100 if done, 0 if not
            logged = progress_map.get(tid)
            if td["status"] == "done":
                td["progress_pct"] = 100
            elif logged is not None:
                td["progress_pct"] = logged
            else:
                td["progress_pct"] = 0
            td["subtask_total"] = 0
            td["subtask_done"] = 0

        td["latest_note"] = note_map.get(tid, "")

        if td["parent_task_id"] is None:
            roots.append(td)

    return roots
