"""Project scope shared by interactive APIs, reports and realtime updates."""
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project
from app.models.project_access import ProjectAccessPolicy
from app.models.task import Task, TaskStatus
from app.models.user import User


async def get_visible_project_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    query = select(Project.id)
    if user.role != "admin":
        private = select(ProjectAccessPolicy.project_id).where(ProjectAccessPolicy.visibility == "private")
        memberships = select(Assignment.project_id).where(Assignment.user_id == user.id,
            Assignment.kind == AssignmentKind.PROJECT_MEMBER)
        query = query.where(or_(~Project.id.in_(private), Project.owner_id == user.id, Project.id.in_(memberships)))
    return list((await db.execute(query)).scalars().all())


async def ensure_project_access(db: AsyncSession, user: User, project_id: uuid.UUID, write: bool = False) -> Project:
    project = await db.get(Project, project_id)
    if not project or project.id not in await get_visible_project_ids(db, user):
        raise HTTPException(404, "Project not found")
    if write and user.role != "admin" and project.owner_id != user.id:
        roles = list((await db.execute(select(Assignment.role).where(
            Assignment.project_id == project_id, Assignment.user_id == user.id,
            Assignment.kind == AssignmentKind.PROJECT_MEMBER,
        ))).scalars().all())
        if roles and all(role == "observer" for role in roles):
            raise HTTPException(403, "项目观察者仅有只读权限")
    return project


async def ensure_task_access(db: AsyncSession, user: User, task_id: uuid.UUID,
                             write: bool = False, include_deleted: bool = False) -> Task:
    task = await db.get(Task, task_id)
    if not task or (task.is_deleted and not include_deleted):
        raise HTTPException(404, "Task not found")
    await ensure_project_access(db, user, task.project_id, write=write)
    return task


async def validate_project_user(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> User:
    candidate = await db.get(User, user_id)
    if not candidate or not candidate.is_active:
        raise HTTPException(400, "请选择有效的在职成员")
    policy = await db.get(ProjectAccessPolicy, project_id)
    if policy and policy.visibility == "private" and project_id not in await get_visible_project_ids(db, candidate):
        raise HTTPException(400, "该成员尚未加入此私有项目")
    roles = list((await db.execute(select(Assignment.role).where(
        Assignment.project_id == project_id, Assignment.user_id == user_id,
        Assignment.kind == AssignmentKind.PROJECT_MEMBER,
    ))).scalars().all())
    project = await db.get(Project, project_id)
    if roles and all(role == "observer" for role in roles) and candidate.role != "admin" and project.owner_id != user_id:
        raise HTTPException(400, "项目观察者不能承担执行或验收责任")
    return candidate


async def require_completed_handover(db: AsyncSession, user_id: uuid.UUID,
                                     project_id: uuid.UUID | None = None) -> None:
    from app.models.task_management import TaskGovernance, TaskIssue
    from app.models.project import ProjectStatus
    unfinished = select(Task.id).join(Project, Task.project_id == Project.id).where(
        Task.is_deleted == False, Task.status != TaskStatus.DONE, Project.status != ProjectStatus.ARCHIVED)
    if project_id is not None:
        unfinished = unfinished.where(Task.project_id == project_id)
    assigned = (await db.execute(select(Assignment.id).where(Assignment.user_id == user_id,
        Assignment.task_id.in_(unfinished)).limit(1))).first()
    reviewing = (await db.execute(select(TaskGovernance.task_id).where(
        TaskGovernance.reviewer_id == user_id, TaskGovernance.task_id.in_(unfinished)).limit(1))).first()
    handling = (await db.execute(select(TaskIssue.id).where(TaskIssue.owner_id == user_id,
        TaskIssue.task_id.in_(unfinished), TaskIssue.state == "open").limit(1))).first()
    if assigned or reviewing or handling:
        raise ValueError("该成员仍承担执行、验收或阻塞处理责任，请先完成交接")
    from app.models.team_planning import ProjectMilestone
    query = select(ProjectMilestone).join(Project, ProjectMilestone.project_id == Project.id).where(
        ProjectMilestone.owner_id == user_id, Project.status != ProjectStatus.ARCHIVED)
    if project_id is not None:
        query = query.where(ProjectMilestone.project_id == project_id)
    for milestone in (await db.execute(query)).scalars():
        linked = [uuid.UUID(value) for value in milestone.task_ids]
        completed = (await db.execute(select(Task.id).where(Task.id.in_(linked),
            Task.status == TaskStatus.DONE, Task.is_deleted == False))).scalars().all() if linked else []
        if not linked or len(set(completed)) != len(set(linked)):
            raise ValueError("该成员仍负责未完成里程碑，请先移交里程碑负责人")


async def can_manage_access(db: AsyncSession, user: User, project: Project) -> bool:
    if user.role == "admin" or project.owner_id == user.id:
        return True
    return bool((await db.execute(select(Assignment.id).where(
        Assignment.project_id == project.id, Assignment.user_id == user.id,
        Assignment.kind == AssignmentKind.PROJECT_MEMBER, Assignment.role == "lead",
    ))).first())


async def scoped_request_access(request: Request, db: AsyncSession = Depends(get_db),
                                user: User = Depends(get_current_user)) -> None:
    """Protect legacy path/body references without changing their response schemas."""
    write = request.method not in {"GET", "HEAD", "OPTIONS"}
    project_ids, task_ids, parent_ids = set(), set(), set()

    def collect(value):
        if isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if item and key in {"project_id"}:
                    project_ids.add(str(item))
                elif item and key == "parent_task_id":
                    parent_ids.add(str(item))
                elif item and key in {"task_id", "predecessor_id", "successor_id"}:
                    task_ids.add(str(item))
    collect(request.path_params)
    if write and request.headers.get("content-type", "").startswith("application/json"):
        try:
            collect(await request.json())
        except ValueError:
            return  # Let the route's request schema report malformed JSON.
    for value in project_ids:
        try:
            parsed = uuid.UUID(value)
        except ValueError:
            raise HTTPException(422, "Project ID is invalid") from None
        await ensure_project_access(db, user, parsed, write=write)
    for value in task_ids | parent_ids:
        try:
            parsed = uuid.UUID(value)
        except ValueError:
            raise HTTPException(422, "Task ID is invalid") from None
        if value not in task_ids and not await db.get(Task, parsed):
            continue  # Existing task validation reports an invalid parent as HTTP 400.
        await ensure_task_access(db, user, parsed, write=write, include_deleted=True)
