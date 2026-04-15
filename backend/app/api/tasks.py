import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_permission, user_has_permission
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.task import (
    TaskAssign, TaskCreate, TaskOut, TaskProgressCreate, TaskProgressOut,
    TaskReorder, TaskStatusUpdate, TaskUpdate,
)
from app.services import task_service
from app.websocket.events import emit_task_event, emit_progress_event

router = APIRouter(tags=["任务"])


async def require_task_update_permissions(db: AsyncSession, user: User, data: TaskUpdate) -> None:
    fields = set(data.model_dump(exclude_unset=True).keys())
    required: set[str] = set()
    if fields & {"title", "description", "priority"}:
        required.add("task.edit")
    if fields & {"assignee_id"}:
        required.add("task.assign")
    if fields & {"deadline"}:
        required.add("task.set_deadline")
    if fields & {"start_date"}:
        required.add("task.set_deadline")
    if fields & {"estimated_hours", "actual_hours"}:
        required.add("task.set_hours")

    for permission in required:
        if not await user_has_permission(db, user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )


@router.get("/projects/{project_id}/tasks", response_model=dict)
async def list_tasks(
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await task_service.list_tasks(db, project_id, status, assignee_id, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    project_id: uuid.UUID,
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.create")),
):
    task = await task_service.create_task(db, project_id, data, current_user.id)
    await db.refresh(task)
    await emit_task_event("task.created", {"task_id": str(task.id), "project_id": str(project_id)})
    return await task_service.task_to_out(db, task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await task_service.task_to_out(db, task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_task_update_permissions(db, current_user, data)
    try:
        task = await task_service.update_task(db, task_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await emit_task_event("task.updated", {"task_id": str(task_id)})
    return await task_service.task_to_out(db, task)


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.delete")),
):
    ok = await task_service.delete_task(db, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.patch("/tasks/{task_id}/status", response_model=TaskOut)
async def update_status(
    task_id: uuid.UUID,
    data: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        task = await task_service.update_task_status(db, task_id, data.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await emit_task_event("task.status_changed", {"task_id": str(task_id), "status": data.status.value})
    return await task_service.task_to_out(db, task)


@router.post("/tasks/{task_id}/signoff", response_model=TaskOut)
async def signoff_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.signoff")),
):
    try:
        task = await task_service.signoff_task(db, task_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await emit_task_event("task.signed_off", {"task_id": str(task_id), "signed_off_by": str(current_user.id)})
    return await task_service.task_to_out(db, task)


@router.patch("/tasks/{task_id}/assign", response_model=TaskOut)
async def assign_task(
    task_id: uuid.UUID,
    data: TaskAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.assign")),
):
    task = await task_service.assign_task(db, task_id, data.assignee_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await emit_task_event("task.assigned", {"task_id": str(task_id), "assignee_id": str(data.assignee_id)})
    return await task_service.task_to_out(db, task)


@router.post("/tasks/{task_id}/progress", response_model=TaskProgressOut, status_code=201)
async def log_progress(
    task_id: uuid.UUID,
    data: TaskProgressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.submit")),
):
    try:
        entry = await task_service.log_progress(
            db, task_id, current_user.id, data.progress_pct, data.note, data.hours_spent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await emit_progress_event({"task_id": str(task_id), "progress_pct": data.progress_pct})
    return {
        "id": entry.id, "task_id": entry.task_id, "user_id": entry.user_id,
        "user_name": current_user.full_name, "progress_pct": entry.progress_pct,
        "note": entry.note, "hours_spent": float(entry.hours_spent) if entry.hours_spent else None,
        "created_at": entry.created_at,
    }


@router.get("/tasks/{task_id}/progress", response_model=list[TaskProgressOut])
async def get_progress(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("progress.view")),
):
    return await task_service.get_progress_history(db, task_id)


@router.patch("/tasks/reorder")
async def reorder_tasks(
    items: list[TaskReorder],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.edit")),
):
    await task_service.reorder_tasks(db, [i.model_dump() for i in items])
    return {"message": "Reordered"}


@router.get("/tasks/{task_id}/subtasks")
async def get_subtasks(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all subtasks of a parent task."""
    return await task_service.get_subtasks(db, task_id)


@router.post("/tasks/{task_id}/subtasks", status_code=201)
async def create_subtask(
    task_id: uuid.UUID,
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.create")),
):
    """Create a subtask under a parent task."""
    parent = await task_service.get_task(db, task_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent task not found")
    data.parent_task_id = task_id
    task = await task_service.create_task(db, parent.project_id, data, current_user.id)
    await db.refresh(task)
    await emit_task_event("task.created", {"task_id": str(task.id), "parent_task_id": str(task_id)})
    return await task_service.task_to_out(db, task)


@router.post("/tasks/{task_id}/batch-subtasks", status_code=201)
async def batch_create_subtasks(
    task_id: uuid.UUID,
    subtasks: list[TaskCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("task.create")),
):
    """Batch create subtasks (used after AI decomposition)."""
    parent = await task_service.get_task(db, task_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent task not found")
    created = []
    for s in subtasks:
        s.parent_task_id = task_id
        task = await task_service.create_task(db, parent.project_id, s, current_user.id)
        await db.refresh(task)
        created.append(await task_service.task_to_out(db, task))
    return created
