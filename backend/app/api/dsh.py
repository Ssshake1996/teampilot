import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.dsh_draft import DshDraft
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.dsh import DraftApprove, DraftCommit, DraftCreate
from app.services import dsh_service as service
from app.services import dsh_query_service as query_service

router = APIRouter(prefix="/integrations/dsh", tags=["DSH"])


@router.get("/tasks")
async def query_tasks(project_id: uuid.UUID | None = None, assignee_id: uuid.UUID | None = None,
    status: TaskStatus | None = None, search: str = Query("", max_length=300),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Read non-deleted tasks in non-archived projects using the logged-in account."""
    return await query_service.query_tasks(db, project_id=project_id, assignee_id=assignee_id,
        status=status, search=search, page=page, page_size=page_size)


@router.get("/progress")
async def query_progress(project_id: uuid.UUID | None = None, task_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = Query(None, description="Progress author, not task assignee"),
    since: datetime | None = Query(None, description="Inclusive UTC lower bound; timezone-less values are UTC"),
    until: datetime | None = Query(None, description="Exclusive UTC upper bound; timezone-less values are UTC"),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("progress.view"))):
    """Read original progress events without generating or saving a report."""
    return await query_service.query_progress(db, project_id=project_id, task_id=task_id,
        user_id=user_id, since=since, until=until, page=page, page_size=page_size)


@router.get("/projects/{project_id}/context")
async def context(project_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.context(db, user, project_id, page, page_size)


@router.post("/drafts", status_code=201)
async def create(data: DraftCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.create_draft(db, user, data)


@router.get("/drafts")
async def list_drafts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(DshDraft).where(DshDraft.author_id == user.id)
        .order_by(DshDraft.created_at.desc(), DshDraft.id).limit(50))).scalars().all()
    return {"items": [service.public_draft(row) for row in rows]}


@router.get("/drafts/{draft_id}")
async def get(draft_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return service.public_draft(await service.owned_draft(db, user, draft_id))


@router.post("/drafts/{draft_id}/approve")
async def approve(draft_id: uuid.UUID, data: DraftApprove, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.approve(db, user, draft_id, data.payload_hash)


@router.post("/drafts/{draft_id}/commit")
async def commit(draft_id: uuid.UUID, data: DraftCommit, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.commit(db, user, draft_id, data.confirmation_token)


@router.post("/drafts/{draft_id}/cancel")
async def cancel(draft_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await service.owned_draft(db, user, draft_id)
    count = (await db.execute(update(DshDraft).where(DshDraft.id == draft_id,
        DshDraft.state.in_(["pending", "approved"]))
        .values(state="cancelled", confirmation_hash=None))).rowcount
    if count != 1:
        raise HTTPException(409, "Draft is no longer pending")
    return {"state": "cancelled"}
