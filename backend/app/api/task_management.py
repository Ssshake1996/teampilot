import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.task_management import (
    DeliveryUpdate, HandoverAccept, IssueCreate, IssueUpdate, ResponsibilityUpdate, ReviewRequest,
)
from app.services import task_management_service as service
from app.services.project_access_service import ensure_project_access, ensure_task_access, get_visible_project_ids

router = APIRouter(prefix="/management/tasks", tags=["团队任务管理"])


async def invoke(action, *args):
    try:
        return await action(*args)
    except service.ManagementError as error:
        raise HTTPException(error.status_code, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get("")
async def list_tasks(project_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if project_id:
        await ensure_project_access(db, user, project_id)
        ids = [project_id]
    else:
        ids = await get_visible_project_ids(db, user)
    return await service.list_tasks(db, ids)


@router.get("/{task_id}")
async def detail(task_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id)
    return await invoke(service.task_detail, db, task_id, user)


@router.put("/{task_id}/responsibility")
async def responsibility(task_id: uuid.UUID, data: ResponsibilityUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id, write=True)
    return await invoke(service.save_responsibility, db, task_id, data, user)


@router.post("/{task_id}/handover/accept")
async def handover(task_id: uuid.UUID, data: HandoverAccept, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id, write=True)
    return await invoke(service.accept_handover, db, task_id, data, user)


@router.put("/{task_id}/delivery")
async def delivery(task_id: uuid.UUID, data: DeliveryUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id, write=True)
    return await invoke(service.save_delivery, db, task_id, data, user)


@router.post("/{task_id}/review")
async def review(task_id: uuid.UUID, data: ReviewRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id, write=True)
    return await invoke(service.review_delivery, db, task_id, data, user)


@router.post("/{task_id}/issues", status_code=201)
async def create_issue(task_id: uuid.UUID, data: IssueCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id, write=True)
    return await invoke(service.create_issue, db, task_id, data, user)


@router.patch("/{task_id}/issues/{issue_id}")
async def update_issue(task_id: uuid.UUID, issue_id: uuid.UUID, data: IssueUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_task_access(db, user, task_id, write=True)
    return await invoke(service.update_issue, db, task_id, issue_id, data, user)
