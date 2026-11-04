import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project_access import ProjectAccessPolicy
from app.models.user import User
from app.models.assignment import Assignment, AssignmentKind
from app.models.task import Task, TaskStatus
from app.models.task_management import TaskGovernance, TaskIssue
from app.services.project_access_service import can_manage_access, ensure_project_access, validate_project_user
from app.websocket.events import queue_project_event

router = APIRouter(prefix="/management/projects", tags=["Project Access"])


class AccessUpdate(BaseModel):
    visibility: Literal["company", "private"] | None = None
    owner_id: uuid.UUID | None = None


@router.get("/{project_id}/access")
async def get_access(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    project = await ensure_project_access(db, user, project_id)
    policy = await db.get(ProjectAccessPolicy, project_id)
    can_write = True
    try:
        await ensure_project_access(db, user, project_id, write=True)
    except HTTPException as error:
        if error.status_code != 403:
            raise
        can_write = False
    return {"project_id": project_id, "visibility": policy.visibility if policy else "company",
            "can_manage": await can_manage_access(db, user, project), "can_write": can_write,
            "owner_id": project.owner_id, "can_transfer_owner": user.role == "admin" or project.owner_id == user.id}


@router.patch("/{project_id}/access")
async def update_access(project_id: uuid.UUID, data: AccessUpdate, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    project = await ensure_project_access(db, user, project_id, write=True)
    if not await can_manage_access(db, user, project):
        raise HTTPException(403, "仅项目负责人、接口人或管理员可更改项目访问范围")
    if data.visibility is None and data.owner_id is None:
        raise HTTPException(400, "请选择访问范围或新的项目负责人")
    if data.owner_id is not None:
        if user.role != "admin" and project.owner_id != user.id:
            raise HTTPException(403, "仅当前项目负责人或管理员可移交项目")
        await validate_project_user(db, project_id, data.owner_id)
        project.owner_id = data.owner_id
    policy = await db.get(ProjectAccessPolicy, project_id)
    if data.visibility == "private":
        members = set((await db.execute(select(Assignment.user_id).where(
            Assignment.project_id == project_id, Assignment.kind == AssignmentKind.PROJECT_MEMBER))).scalars())
        admins = set((await db.execute(select(User.id).where(User.role == "admin", User.is_active == True))).scalars())
        live = select(Task.id).where(Task.project_id == project_id, Task.is_deleted == False, Task.status != TaskStatus.DONE)
        responsible = set((await db.execute(select(Assignment.user_id).where(Assignment.task_id.in_(live)))).scalars())
        responsible.update((await db.execute(select(TaskGovernance.reviewer_id).where(TaskGovernance.task_id.in_(live)))).scalars())
        responsible.update((await db.execute(select(TaskIssue.owner_id).where(TaskIssue.task_id.in_(live), TaskIssue.state == "open"))).scalars())
        if responsible - members - admins - {project.owner_id}:
            raise HTTPException(400, "仍有执行、验收或阻塞处理人未加入项目，请先添加为项目成员再设为私有")
    if policy and data.visibility is not None:
        policy.visibility = data.visibility
        policy.updated_by_id = user.id
    elif data.visibility is not None:
        db.add(ProjectAccessPolicy(project_id=project_id, visibility=data.visibility, updated_by_id=user.id))
    await db.flush()
    queue_project_event(db)
    return await get_access(project_id=project_id, db=db, user=user)
