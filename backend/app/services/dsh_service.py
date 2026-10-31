"""Business drafts, not an agent runtime. All commits reuse existing services."""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import user_has_permission
from app.models.assignment import Assignment
from app.models.dsh_draft import DshDraft
from app.models.project import Project, ProjectStatus
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.models.user import User
from app.schemas.dsh import DraftCreate, ProjectPlan, ProgressDraft, TaskCreateDraft
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import project_service, task_service


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def permission(db, user, code):
    if not await user_has_permission(db, user, code):
        raise HTTPException(403, f"Permission required: {code}")


async def project_revision(db: AsyncSession, project: Project) -> str:
    # Counts catch same-second progress submissions, including identical percentages.
    tasks = (await db.execute(select(Task.__table__).where(Task.project_id == project.id)
        .order_by(Task.id))).mappings().all()
    assignments = (await db.execute(select(Assignment.__table__).where(Assignment.project_id == project.id)
        .order_by(Assignment.id))).mappings().all()
    events = (await db.execute(select(TaskEvent.task_id, func.count(TaskEvent.id), func.max(TaskEvent.created_at))
        .join(Task, TaskEvent.task_id == Task.id).where(Task.project_id == project.id)
        .group_by(TaskEvent.task_id).order_by(TaskEvent.task_id))).all()
    return digest({"project": {col.name: getattr(project, col.name) for col in Project.__table__.columns},
        "tasks": [dict(row) for row in tasks], "assignments": [dict(row) for row in assignments],
        "events": [list(row) for row in events]})


async def get_project(db, project_id, *, lock=False):
    query = select(Project).where(Project.id == project_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    project = (await db.execute(query)).scalar_one_or_none()
    if not project or project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(404, "Active project not found")
    return project


async def context(db, user, project_id, page, page_size):
    await permission(db, user, "progress.view")
    project = await get_project(db, project_id)
    tasks, total = await task_service.list_tasks(db, project_id, page=page, page_size=page_size)
    # No credentials, unbounded histories, connector secrets, or role configuration.
    return {"project": await project_service.project_to_out(db, project),
        "revision": await project_revision(db, project), "tasks": tasks,
        "total": total, "page": page, "page_size": page_size,
        "truncated": page_size * page < total or page > 1}


async def validate_payload(db, user, payload, *, lock=False):
    if isinstance(payload, (ProjectPlan, TaskCreateDraft)):
        if isinstance(payload, ProjectPlan):
            await permission(db, user, "project.create")
        else:
            project = await get_project(db, payload.project_id, lock=lock)
            if await project_revision(db, project) != payload.revision:
                raise HTTPException(409, "Project changed; generate a new draft")
            if payload.parent_task_id:
                parent = await task_service.get_task(db, payload.parent_task_id)
                if not parent or parent.is_deleted or parent.project_id != project.id:
                    raise HTTPException(400, "Parent must be an active task in the selected project")
        await permission(db, user, "task.create")
        stack = list(payload.tasks)
        nodes = []
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(node.children)
        if any(node.assignee_ids for node in nodes):
            await permission(db, user, "task.assign")
        if any(node.start_date or node.deadline for node in nodes):
            await permission(db, user, "task.set_deadline")
        if any(node.estimated_hours is not None for node in nodes):
            await permission(db, user, "task.set_hours")
    else:
        project = await get_project(db, payload.project_id, lock=lock)
        if await project_revision(db, project) != payload.revision:
            raise HTTPException(409, "Project changed; generate a new draft")
        ids = [entry.task_id for entry in payload.updates] if isinstance(payload, ProgressDraft) else [payload.task_id]
        tasks = (await db.execute(select(Task).where(Task.id.in_(ids),
            Task.project_id == payload.project_id, Task.is_deleted == False))).scalars().all()
        if len(tasks) != len(ids):
            raise HTTPException(400, "Every task must belong to the selected active project")
        if isinstance(payload, ProgressDraft):
            await permission(db, user, "progress.submit")
            nodes = []
        else:
            from app.api.tasks import require_task_update_permissions
            await require_task_update_permissions(db, user, TaskUpdate(**payload.patch.model_dump(exclude_unset=True)))
            nodes = [payload.patch]
            existing = tasks[0]
            start = payload.patch.start_date if "start_date" in payload.patch.model_fields_set else existing.start_date
            end = payload.patch.deadline if "deadline" in payload.patch.model_fields_set else existing.deadline
            if start and end and aware(start) > aware(end):
                raise HTTPException(400, "Task deadline precedes start")
    ids = {uid for node in nodes for uid in node.assignee_ids}
    if ids:
        found = set((await db.execute(select(User.id).where(User.id.in_(ids), User.is_active == True))).scalars())
        if found != ids:
            raise HTTPException(400, "Assignees must be active users")
    for node in nodes:
        if node.start_date and node.deadline and aware(node.start_date) > aware(node.deadline):
            raise HTTPException(400, "Task deadline precedes start")


def public_draft(draft):
    return {"id": draft.id, "payload": draft.payload, "payload_hash": draft.payload_hash,
        "preview": draft.preview, "state": draft.state, "expires_at": aware(draft.expires_at),
        "approval_expires_at": aware(draft.approval_expires_at) if draft.approval_expires_at else None,
        "result": draft.result}


async def owned_draft(db, user, draft_id):
    draft = (await db.execute(select(DshDraft).where(DshDraft.id == draft_id,
        DshDraft.author_id == user.id).execution_options(populate_existing=True))).scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Draft not found")
    return draft


async def create_draft(db, user, data):
    await validate_payload(db, user, data.payload)
    payload = data.payload.model_dump(mode="json", exclude_unset=True)
    items = []
    if isinstance(data.payload, (ProjectPlan, TaskCreateDraft)):
        stack = list(data.payload.tasks)
        while stack:
            node = stack.pop()
            items.append({"title": node.title, "before": None, "after": node.model_dump(mode="json", exclude={"children"})})
            stack.extend(node.children)
    else:
        entries = data.payload.updates if isinstance(data.payload, ProgressDraft) else [data.payload]
        progress = await task_service.get_project_task_progress_map(db, data.payload.project_id)
        for entry in entries:
            task = await task_service.get_task(db, entry.task_id)
            if isinstance(data.payload, ProgressDraft):
                before = {"progress_pct": progress.get(task.id, 0)}
                after = entry.model_dump(mode="json", exclude={"task_id"})
            else:
                after = entry.patch.model_dump(mode="json", exclude_unset=True)
                assignees = await task_service.get_task_assignee_map(db, [task])
                before = {key: [str(item["user_id"]) for item in assignees.get(task.id, [])]
                    if key == "assignee_ids" else str(getattr(task, key)) if getattr(task, key) is not None else None for key in after}
            items.append({"title": task.title, "before": before, "after": after})
    # Display names are a review snapshot only; UUIDs remain in the exact payload
    # checked by approval and commit. Never include credentials or confirmation secrets.
    assignee_ids = {uuid.UUID(uid) for item in items for side in ("before", "after")
        for uid in (item[side] or {}).get("assignee_ids", [])}
    display_names = {str(uid): name for uid, name in (await db.execute(
        select(User.id, User.full_name).where(User.id.in_(assignee_ids)))).all()} if assignee_ids else {}
    preview = {"items": items, "display_names": display_names}
    if not isinstance(data.payload, ProjectPlan):
        preview["project_name"] = (await get_project(db, data.payload.project_id)).name
    if isinstance(data.payload, (ProjectPlan, TaskCreateDraft)):
        preview["weight_policy"] = "Sibling weights are rebalanced equally; completed ancestors reopen when children are added."
    draft = DshDraft(author_id=user.id, payload=payload, payload_hash=digest(payload), preview=preview,
        expires_at=now() + timedelta(hours=1))
    db.add(draft)
    await db.flush()
    return public_draft(draft)


async def approve(db, user, draft_id, payload_hash):
    draft = await owned_draft(db, user, draft_id)
    if draft.payload_hash != payload_hash or draft.state not in ("pending", "approved") or aware(draft.expires_at) <= now():
        raise HTTPException(409, "Draft changed, expired, or no longer pending")
    await validate_payload(db, user, DraftCreate(payload=draft.payload).payload)
    token = secrets.token_hex(32)
    count = (await db.execute(update(DshDraft).where(DshDraft.id == draft_id,
        DshDraft.state.in_(["pending", "approved"])).values(state="approved",
        confirmation_hash=digest(token), approval_expires_at=now() + timedelta(minutes=5)))).rowcount
    if count != 1:
        raise HTTPException(409, "Draft is no longer pending")
    return {"confirmation_token": token, "state": "approved"}


async def commit(db, user, draft_id, token):
    draft = await owned_draft(db, user, draft_id)
    if not draft.confirmation_hash or not secrets.compare_digest(draft.confirmation_hash, digest(token)):
        raise HTTPException(403, "Explicit approval required")
    if draft.state == "committed":
        return draft.result
    if draft.state != "approved" or aware(draft.expires_at) <= now() or not draft.approval_expires_at or aware(draft.approval_expires_at) <= now():
        raise HTTPException(409, "Approval expired or consumed")
    # Atomic claim serializes SQLite writers and prevents two tokens committing once.
    count = (await db.execute(update(DshDraft).where(DshDraft.id == draft_id,
        DshDraft.state == "approved", DshDraft.confirmation_hash == digest(token))
        .values(state="committing"))).rowcount
    if count != 1:
        raise HTTPException(409, "Concurrent draft commit")
    payload = DraftCreate(payload=draft.payload).payload
    await validate_payload(db, user, payload, lock=True)
    result = {"draft_id": str(draft.id), "kind": payload.kind, "task_ids": []}
    try:
        if isinstance(payload, (ProjectPlan, TaskCreateDraft)):
            if isinstance(payload, ProjectPlan):
                project = await project_service.create_project(db, ProjectCreate(**payload.model_dump(exclude={"kind", "tasks"})), user.id)
                project_id, parent_id = project.id, None
            else:
                project_id, parent_id = payload.project_id, payload.parent_task_id
            result["project_id"] = str(project_id)
            async def create_nodes(nodes, parent_id=None):
                for node in nodes:
                    task = await task_service.create_task(db, project_id,
                        TaskCreate(**node.model_dump(exclude={"children"}), parent_task_id=parent_id), user.id)
                    result["task_ids"].append(str(task.id))
                    await create_nodes(node.children, task.id)
            await create_nodes(payload.tasks, parent_id)
        elif isinstance(payload, ProgressDraft):
            for entry in payload.updates:
                await task_service.log_progress(db, entry.task_id, user.id, entry.progress_pct, entry.note, entry.hours_spent)
                result["task_ids"].append(str(entry.task_id))
            result["project_id"] = str(payload.project_id)
        else:
            await task_service.update_task(db, payload.task_id, TaskUpdate(**payload.patch.model_dump(exclude_unset=True)))
            result["task_ids"] = [str(payload.task_id)]
            result["project_id"] = str(payload.project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    draft.state = "committed"
    draft.result = result
    await db.flush()
    return result
