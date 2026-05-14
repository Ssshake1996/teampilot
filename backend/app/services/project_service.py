import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectRole, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.task_service import (
    effective_task_status,
    get_project_task_progress_map,
    get_task_assignee_map,
)


async def get_project_member_count(db: AsyncSession, project_id: uuid.UUID) -> int:
    member_union = union(
        select(Assignment.user_id.label("user_id")).where(
            Assignment.project_id == project_id,
            Assignment.kind == AssignmentKind.PROJECT_MEMBER,
        ),
        select(Assignment.user_id.label("user_id"))
        .join(Task, Assignment.task_id == Task.id)
        .where(
            Assignment.project_id == project_id,
            Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
            Task.is_deleted == False,
        ),
    ).subquery()
    return (
        await db.execute(select(func.count()).select_from(member_union))
    ).scalar() or 0


async def get_project_contact_map(db: AsyncSession, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    if not project_ids:
        return {}
    rows = (
        await db.execute(
            select(Assignment.project_id, Assignment.user_id, User.full_name)
            .join(User, Assignment.user_id == User.id)
            .where(
                Assignment.project_id.in_(project_ids),
                Assignment.kind == AssignmentKind.PROJECT_MEMBER,
                Assignment.role == ProjectRole.LEAD.value,
            )
        )
    ).all()
    contact_map: dict[uuid.UUID, list[dict]] = {project_id: [] for project_id in project_ids}
    seen_by_project: dict[uuid.UUID, set[uuid.UUID]] = {project_id: set() for project_id in project_ids}
    for project_id, user_id, full_name in rows:
        if user_id in seen_by_project.setdefault(project_id, set()):
            continue
        seen_by_project[project_id].add(user_id)
        contact_map.setdefault(project_id, []).append({
            "user_id": user_id,
            "full_name": full_name,
        })

    for contacts in contact_map.values():
        contacts.sort(key=lambda item: ((item["full_name"] or ""), str(item["user_id"])))
    return contact_map


async def effective_project_status(db: AsyncSession, project: Project) -> ProjectStatus:
    if project.status == ProjectStatus.ARCHIVED:
        return ProjectStatus.ARCHIVED

    tasks = (
        await db.execute(
            select(Task).where(
                Task.project_id == project.id,
                Task.is_deleted == False,
            )
        )
    ).scalars().all()

    if not tasks:
        return ProjectStatus.PLANNING

    statuses = [effective_task_status(task) for task in tasks]
    if all(status == TaskStatus.DONE for status in statuses):
        return ProjectStatus.COMPLETED
    if all(status == TaskStatus.NOT_STARTED for status in statuses):
        return ProjectStatus.PLANNING
    return ProjectStatus.ACTIVE


async def sync_project_status(db: AsyncSession, project: Project) -> ProjectStatus:
    status = await effective_project_status(db, project)
    if project.status != status:
        project.status = status
        await db.flush()
    return status


async def project_to_out(db: AsyncSession, project: Project) -> dict:
    task_count = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project.id,
                Task.is_deleted == False,
            )
        )
    ).scalar() or 0
    done_count = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project.id,
                Task.status == TaskStatus.DONE,
                Task.is_deleted == False,
            )
        )
    ).scalar() or 0
    member_count = await get_project_member_count(db, project.id)
    status = await sync_project_status(db, project)
    owner_name = (
        await db.execute(select(User.full_name).where(User.id == project.owner_id))
    ).scalar()
    contacts = (await get_project_contact_map(db, [project.id])).get(project.id, [])
    if not contacts and owner_name:
        contacts = [{"user_id": project.owner_id, "full_name": owner_name}]
    return {
        "id": project.id,
        "name": project.name,
        "goal": project.goal,
        "description": project.description,
        "status": status,
        "owner_id": project.owner_id,
        "owner_name": owner_name,
        "contact_user_ids": [item["user_id"] for item in contacts],
        "contact_names": [item["full_name"] for item in contacts if item["full_name"]],
        "start_date": project.start_date,
        "end_date": project.end_date,
        "created_at": project.created_at,
        "task_count": task_count,
        "completed_count": done_count,
        "member_count": member_count,
    }


async def list_projects(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    include_archived: bool = False,
) -> tuple[list[dict], int]:
    base_filter = [] if include_archived else [Project.status != ProjectStatus.ARCHIVED]

    total = (await db.execute(select(func.count(Project.id)).where(*base_filter))).scalar()
    projects = (
        await db.execute(
            select(Project)
            .where(*base_filter)
            .order_by(Project.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = []
    for project in projects:
        items.append(await project_to_out(db, project))
    return items, total


async def create_project(db: AsyncSession, data: ProjectCreate, owner_id: uuid.UUID) -> Project:
    project = Project(**data.model_dump(), owner_id=owner_id)
    db.add(project)
    await db.flush()
    db.add(Assignment(
        project_id=project.id,
        user_id=owner_id,
        kind=AssignmentKind.PROJECT_MEMBER,
        role=ProjectRole.LEAD.value,
    ))
    await db.flush()
    return project


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()


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
    explicit_rows = (
        await db.execute(
            select(Assignment, User)
            .join(User, Assignment.user_id == User.id)
            .where(
                Assignment.project_id == project_id,
                Assignment.kind == AssignmentKind.PROJECT_MEMBER,
            )
        )
    ).all()

    member_by_user: dict[uuid.UUID, dict] = {}
    valid_roles = {role.value for role in ProjectRole}
    for assignment, user in explicit_rows:
        role = assignment.role if assignment.role in valid_roles else ProjectRole.MEMBER.value
        member_by_user[assignment.user_id] = {
            "user_id": assignment.user_id,
            "full_name": user.full_name,
            "role_in_project": role,
        }

    assignee_rows = (
        await db.execute(
            select(Assignment, User)
            .join(User, Assignment.user_id == User.id)
            .join(Task, Assignment.task_id == Task.id)
            .where(
                Assignment.project_id == project_id,
                Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
                Task.is_deleted == False,
            )
        )
    ).all()
    for assignment, user in assignee_rows:
        member_by_user.setdefault(assignment.user_id, {
            "user_id": assignment.user_id,
            "full_name": user.full_name,
            "role_in_project": ProjectRole.MEMBER.value,
        })

    return sorted(
        member_by_user.values(),
        key=lambda item: ((item["full_name"] or ""), str(item["user_id"])),
    )


async def add_project_member(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
) -> None:
    existing = (
        await db.execute(
            select(Assignment).where(
                Assignment.project_id == project_id,
                Assignment.user_id == user_id,
                Assignment.kind == AssignmentKind.PROJECT_MEMBER,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.role = role
    else:
        db.add(Assignment(
            project_id=project_id,
            user_id=user_id,
            kind=AssignmentKind.PROJECT_MEMBER,
            role=role,
        ))
    await db.flush()


async def remove_project_member(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await db.execute(
        delete(Assignment).where(
            Assignment.project_id == project_id,
            Assignment.user_id == user_id,
            Assignment.kind == AssignmentKind.PROJECT_MEMBER,
        )
    )
    await db.flush()


async def get_project_task_tree(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    now = datetime.utcnow()
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.sort_order, Task.created_at)
        )
    ).scalars().all()
    assignee_map = await get_task_assignee_map(db, tasks)
    computed_progress_map = {
        str(task_id): progress
        for task_id, progress in (await get_project_task_progress_map(db, project_id)).items()
    }

    all_tasks: dict[str, dict] = {}
    children_map: dict[str, list[dict]] = {}
    for task in tasks:
        status = effective_task_status(task).value
        assignees = assignee_map.get(task.id, [])
        assignee_names = [item["full_name"] for item in assignees if item["full_name"]]
        task_dict = {
            "id": str(task.id),
            "title": task.title,
            "goal": task.goal,
            "description": task.description,
            "status": status,
            "priority": task.priority.value,
            "assignee_name": ", ".join(assignee_names) if assignee_names else None,
            "assignee_ids": [str(item["user_id"]) for item in assignees],
            "assignee_names": assignee_names,
            "estimated_hours": float(task.estimated_hours) if task.estimated_hours else None,
            "actual_hours": float(task.actual_hours) if task.actual_hours else None,
            "start_date": (task.start_date or task.created_at).isoformat() if (task.start_date or task.created_at) else None,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "signed_off_by_id": str(task.signed_off_by_id) if task.signed_off_by_id else None,
            "signed_off_at": task.signed_off_at.isoformat() if task.signed_off_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
            "weight": float(task.weight) if task.weight is not None else 1.0,
            "is_deleted": bool(task.is_deleted),
            "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "is_overdue": bool(
                not task.is_deleted
                and task.deadline
                and task.deadline.replace(tzinfo=None) < now
                and status != "done"
            ),
            "children": [],
        }
        all_tasks[str(task.id)] = task_dict
        if task.parent_task_id:
            children_map.setdefault(str(task.parent_task_id), []).append(task_dict)

    progress_map: dict[str, int] = {}
    note_map: dict[str, str] = {}
    progress_rows = (
        await db.execute(
            select(TaskEvent.task_id, TaskEvent.progress_pct, TaskEvent.note)
            .join(Task, TaskEvent.task_id == Task.id)
            .where(Task.project_id == project_id)
            .where(
                TaskEvent.event_type == TaskEventType.PROGRESS,
                TaskEvent.progress_pct.isnot(None),
            )
            .order_by(TaskEvent.created_at.desc())
        )
    ).all()
    for task_id, progress_pct, note in progress_rows:
        task_id_str = str(task_id)
        if task_id_str not in progress_map:
            progress_map[task_id_str] = progress_pct
            note_map[task_id_str] = note or ""

    roots = []
    for task_id, task_dict in all_tasks.items():
        task_dict["children"] = children_map.get(task_id, [])
        children = task_dict["children"]

        active_children = [child for child in children if not child.get("is_deleted")]
        task_dict["progress_pct"] = computed_progress_map.get(task_id, 0)
        task_dict["subtask_total"] = len(active_children)
        task_dict["subtask_done"] = sum(1 for child in active_children if child["status"] == "done")

        task_dict["latest_note"] = note_map.get(task_id, "")

        if task_dict["parent_task_id"] is None:
            roots.append(task_dict)

    return roots
