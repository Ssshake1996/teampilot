import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.project import (
    ProjectCreate, ProjectMemberAdd, ProjectMemberOut, ProjectOut, ProjectUpdate,
)
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["项目"])


@router.get("", response_model=dict)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await project_service.list_projects(db, page, page_size, include_archived)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("project.create")),
):
    project = await project_service.create_project(db, data, current_user.id)
    return {
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        "task_count": 0, "completed_count": 0, "member_count": 1,
    }


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        "task_count": 0, "completed_count": 0, "member_count": 0,
    }


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("project.edit")),
):
    project = await project_service.update_project(db, project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        **{c.name: getattr(project, c.name) for c in project.__table__.columns},
        "task_count": 0, "completed_count": 0, "member_count": 0,
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("project.archive")),
):
    ok = await project_service.delete_project(db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project archived"}


@router.get("/{project_id}/task-tree")
async def get_project_task_tree(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get project tasks in a tree structure (parent tasks with subtask children)."""
    return await project_service.get_project_task_tree(db, project_id)


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
async def get_members(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await project_service.get_project_members(db, project_id)


@router.post("/{project_id}/members", status_code=201)
async def add_member(
    project_id: uuid.UUID,
    data: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("project.member.manage")),
):
    await project_service.add_project_member(db, project_id, data.user_id, data.role_in_project.value)
    return {"message": "Member added"}


@router.delete("/{project_id}/members/{user_id}")
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("project.member.manage")),
):
    await project_service.remove_project_member(db, project_id, user_id)
    return {"message": "Member removed"}
