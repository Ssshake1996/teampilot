import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMember, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


async def list_projects(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    total_q = await db.execute(select(func.count(Project.id)))
    total = total_q.scalar()

    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    projects = result.scalars().all()

    items = []
    for p in projects:
        task_count_q = await db.execute(select(func.count(Task.id)).where(Task.project_id == p.id))
        task_count = task_count_q.scalar()
        done_count_q = await db.execute(
            select(func.count(Task.id)).where(Task.project_id == p.id, Task.status == TaskStatus.DONE)
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
