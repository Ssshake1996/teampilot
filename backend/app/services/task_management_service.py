"""Task responsibility, handover, evidence review and persistent blockers."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import user_has_permission
from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_management import TaskChange, TaskGovernance, TaskIssue
from app.models.user import User
from app.services import task_service
from app.websocket.events import queue_project_event


class ManagementError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def serial(value):
    if isinstance(value, datetime):
        return aware(value).isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, list):
        return [serial(item) for item in value]
    return value


async def record_change(db, task_id, actor_id, before, after, reason):
    before, after = ({key: serial(value) for key, value in values.items()} for values in (before, after))
    if before != after and actor_id:
        db.add(TaskChange(task_id=task_id, actor_id=actor_id, before_json=before,
                          after_json=after, reason=(reason or "").strip() or "通过任务编辑调整", created_at=now()))


async def get_governance(db, task_id):
    # Refresh server-side updated_at after an UPDATE; avoid implicit async IO
    # while serializing a cached ORM object.
    return (await db.execute(select(TaskGovernance).where(TaskGovernance.task_id == task_id)
                             .execution_options(populate_existing=True))).scalar_one_or_none()


async def active_task(db, task_id, *, lock=False):
    task = await task_service.get_task(db, task_id)
    if not task:
        raise ManagementError("任务不存在", 404)
    if lock:
        await task_service.lock_project(db, task)
        if task.is_deleted:
            raise ManagementError("任务已删除", 404)
    return task


async def validate_users(db, project_id, user_ids):
    ids = set(user_ids)
    users = (await db.execute(select(User).where(User.id.in_(ids), User.is_active == True))).scalars().all()
    if len(users) != len(ids):
        raise ManagementError("负责人、协作者和验收人须为有效用户")
    # Project access validation is shared with ordinary task assignment.
    from app.services.project_access_service import validate_project_user
    for user_id in ids:
        await validate_project_user(db, project_id, user_id)


async def permission_flags(db, actor, governance):
    can_manage = await user_has_permission(db, actor, "task.assign")
    return {
        "can_manage": can_manage,
        "can_deliver": bool(governance and (governance.owner_id == actor.id or can_manage)),
        "can_review": bool(governance and governance.reviewer_id == actor.id),
        "can_accept_handover": bool(governance and governance.owner_id == actor.id),
    }


async def task_detail(db, task_id, actor):
    task = await active_task(db, task_id)
    governance = await get_governance(db, task_id)
    issues = (await db.execute(select(TaskIssue).where(TaskIssue.task_id == task_id).order_by(TaskIssue.created_at.desc()))).scalars().all()
    changes = (await db.execute(select(TaskChange).where(TaskChange.task_id == task_id).order_by(TaskChange.created_at.desc(), TaskChange.id.desc()))).scalars().all()
    ids = {item.owner_id for item in issues} | {item.actor_id for item in changes}
    if governance:
        ids.update({governance.owner_id, governance.reviewer_id})
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all()) if ids else {}
    project = await db.get(Project, task.project_id)
    governance_out = None
    if governance:
        governance_out = {column.name: getattr(governance, column.name) for column in governance.__table__.columns}
        governance_out.update(owner_name=names.get(governance.owner_id), reviewer_name=names.get(governance.reviewer_id))
    flags = await permission_flags(db, actor, governance)
    from fastapi import HTTPException
    from app.services.project_access_service import ensure_project_access
    try:
        await ensure_project_access(db, actor, task.project_id, write=True)
    except HTTPException as error:
        if error.status_code != 403:
            raise
        flags = {key: False for key in flags}
    return {
        "task": await task_service.task_to_out(db, task), "governance": governance_out,
        "issues": [issue_out(issue, names, project.owner_id) for issue in issues],
        "changes": [{**{column.name: getattr(change, column.name) for column in change.__table__.columns},
                     "actor_name": names.get(change.actor_id)} for change in changes],
        "needs_owner": governance is None,
        **flags,
    }


def issue_out(issue, names, escalation_owner_id):
    return {**{column.name: getattr(issue, column.name) for column in issue.__table__.columns},
            "owner_name": names.get(issue.owner_id),
            "is_overdue": issue.state == "open" and aware(issue.due_at) < now(),
            "escalation_owner_id": escalation_owner_id}


async def list_tasks(db, project_ids):
    if not project_ids:
        return []
    tasks = (await db.execute(select(Task).where(Task.project_id.in_(project_ids), Task.is_deleted == False)
                             .order_by(Task.created_at.desc()))).scalars().all()
    governance = {item.task_id: item for item in (await db.execute(select(TaskGovernance).where(TaskGovernance.task_id.in_([task.id for task in tasks])))).scalars()}
    users = dict((await db.execute(select(User.id, User.full_name))).all())
    counts = dict((await db.execute(select(TaskIssue.task_id, func.count(TaskIssue.id)).where(
        TaskIssue.task_id.in_([task.id for task in tasks]), TaskIssue.state == "open").group_by(TaskIssue.task_id))).all())
    assignees = await task_service.get_task_assignee_map(db, tasks)
    signers = await task_service.get_signer_names(db, tasks)
    progress = {}
    for project_id in set(task.project_id for task in tasks):
        progress.update(await task_service.get_project_task_progress_map(db, project_id))
    result = []
    for task in tasks:
        meta = governance.get(task.id)
        result.append({**await task_service.task_to_out(db, task, assignee_map=assignees, progress_map=progress, signer_names=signers),
                       "owner_id": meta.owner_id if meta else None, "owner_name": users.get(meta.owner_id) if meta else None,
                       "reviewer_id": meta.reviewer_id if meta else None, "reviewer_name": users.get(meta.reviewer_id) if meta else None,
                       "review_status": meta.review_status if meta else "not_submitted", "needs_owner": meta is None,
                       "open_issue_count": counts.get(task.id, 0), "handover_pending": bool(meta and not meta.handover_accepted_at)})
    return result


async def save_responsibility(db, task_id, data, actor):
    task = await active_task(db, task_id, lock=True)
    if not await user_has_permission(db, actor, "task.assign"):
        raise ManagementError("没有分配任务责任的权限", 403)
    collaborators = [value for value in dict.fromkeys(data.collaborator_ids) if value != data.owner_id]
    await validate_users(db, task.project_id, [data.owner_id, data.reviewer_id, *collaborators])
    meta = await get_governance(db, task_id)
    before = {"owner_id": meta.owner_id if meta else None, "reviewer_id": meta.reviewer_id if meta else None,
              "acceptance_criteria": meta.acceptance_criteria if meta else None,
              "assignee_ids": sorted(str(item["user_id"]) for item in (await task_service.get_task_assignee_map(db, [task]))[task.id])}
    after = {"owner_id": data.owner_id, "reviewer_id": data.reviewer_id,
             "acceptance_criteria": data.acceptance_criteria,
             "assignee_ids": sorted(str(value) for value in [data.owner_id, *collaborators])}
    if meta and all(serial(before[key]) == serial(after[key]) for key in before):
        return await task_detail(db, task_id, actor)
    owner_changed = not meta or meta.owner_id != data.owner_id
    scope_changed = bool(meta and meta.acceptance_criteria != data.acceptance_criteria)
    if not meta:
        meta = TaskGovernance(task_id=task.id, owner_id=data.owner_id, reviewer_id=data.reviewer_id,
                              acceptance_criteria=data.acceptance_criteria, review_status="not_submitted")
        db.add(meta)
    else:
        if task.status == TaskStatus.DONE:
            await task_service.reopen_ancestors(db, task.id, actor.id)
        meta.owner_id, meta.reviewer_id = data.owner_id, data.reviewer_id
        meta.acceptance_criteria = data.acceptance_criteria
        meta.review_status = "not_submitted"
        meta.review_note = None
    if owner_changed or scope_changed:
        meta.handover_accepted_at = None
    await task_service.sync_task_assignees(db, task, [data.owner_id, *collaborators])
    assignments = (await db.execute(select(Assignment).where(Assignment.task_id == task_id,
        Assignment.kind == AssignmentKind.TASK_ASSIGNEE))).scalars().all()
    for assignment in assignments:
        assignment.role = "owner" if assignment.user_id == data.owner_id else "collaborator"
    await record_change(db, task_id, actor.id, before, after, data.change_reason)
    await db.flush()
    queue_project_event(db, task.project_id)
    return await task_detail(db, task_id, actor)


async def accept_handover(db, task_id, data, actor):
    task = await active_task(db, task_id, lock=True)
    meta = await get_governance(db, task_id)
    if not meta or meta.owner_id != actor.id:
        raise ManagementError("只有新主责可以确认接受交接", 403)
    if meta.handover_accepted_at:
        return await task_detail(db, task_id, actor)
    meta.handover_accepted_at = now()
    await record_change(db, task_id, actor.id, {"handover_accepted": False}, {"handover_accepted": True}, data.note or "主责确认接受任务")
    await db.flush()
    queue_project_event(db, task.project_id)
    return await task_detail(db, task_id, actor)


async def save_delivery(db, task_id, data, actor):
    task = await active_task(db, task_id, lock=True)
    meta = await get_governance(db, task_id)
    if not meta or not (await permission_flags(db, actor, meta))["can_deliver"]:
        raise ManagementError("只有主责或任务管理者可以提交成果", 403)
    if not meta.handover_accepted_at:
        raise ManagementError("主责须先确认接受任务")
    if not (data.deliverable_url or (data.deliverable_note or "").strip()):
        raise ManagementError("请提交成果链接或可核验的成果说明")
    if task.status == TaskStatus.DONE:
        await task_service.reopen_ancestors(db, task.id, actor.id)
    before = {"deliverable_url": meta.deliverable_url, "deliverable_note": meta.deliverable_note, "review_status": meta.review_status}
    meta.deliverable_url = data.deliverable_url
    meta.deliverable_note = (data.deliverable_note or "").strip() or None
    meta.review_status, meta.review_note = "submitted", None
    await record_change(db, task_id, actor.id, before,
                        {"deliverable_url": meta.deliverable_url, "deliverable_note": meta.deliverable_note, "review_status": "submitted"}, "提交成果验收")
    await db.flush()
    queue_project_event(db, task.project_id)
    return await task_detail(db, task_id, actor)


async def review_delivery(db, task_id, data, actor):
    task = await active_task(db, task_id, lock=True)
    meta = await get_governance(db, task_id)
    if not meta or meta.reviewer_id != actor.id:
        raise ManagementError("只有指定验收人可以处理验收", 403)
    if meta.review_status != "submitted":
        raise ManagementError("请先提交待验收成果")
    if data.decision == "return" and not data.note.strip():
        raise ManagementError("退回时必须说明未满足的验收项")
    before = {"review_status": meta.review_status, "review_note": meta.review_note}
    meta.review_status = "accepted" if data.decision == "accept" else "changes_requested"
    meta.review_note = data.note.strip() or "按验收标准确认通过"
    if data.decision == "accept":
        await task_service.signoff_task(db, task_id, actor.id)
    await record_change(db, task_id, actor.id, before,
                        {"review_status": meta.review_status, "review_note": meta.review_note}, meta.review_note)
    await db.flush()
    queue_project_event(db, task.project_id)
    return await task_detail(db, task_id, actor)


async def create_issue(db, task_id, data, actor):
    task = await active_task(db, task_id, lock=True)
    if not await user_has_permission(db, actor, "progress.submit"):
        raise ManagementError("没有报告任务问题的权限", 403)
    await validate_users(db, task.project_id, [data.owner_id])
    if task.status == TaskStatus.DONE:
        await task_service.reopen_ancestors(db, task.id, actor.id)
    issue = TaskIssue(task_id=task_id, reporter_id=actor.id, **data.model_dump(), state="open")
    db.add(issue)
    await record_change(db, task_id, actor.id, {}, {"issue_title": data.title, "state": "open", "issue_owner_id": data.owner_id}, "登记任务阻塞")
    await db.flush()
    queue_project_event(db, task.project_id)
    return await task_detail(db, task_id, actor)


async def update_issue(db, task_id, issue_id, data, actor):
    task = await active_task(db, task_id, lock=True)
    issue = await db.get(TaskIssue, issue_id)
    if not issue or issue.task_id != task_id:
        raise ManagementError("问题不存在", 404)
    if actor.id not in (issue.owner_id, issue.reporter_id) and not await user_has_permission(db, actor, "task.assign"):
        raise ManagementError("只有处理人、报告人或任务管理者可以更新问题", 403)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "owner_id" in changes:
        await validate_users(db, task.project_id, [changes["owner_id"]])
    if changes.get("state") == "resolved" and not (changes.get("resolution") or (issue.resolution if issue.state == "resolved" else "") or "").strip():
        raise ManagementError("解除阻塞必须记录解决结果")
    if changes.get("state") == "open":
        changes["resolution"] = None
        if task.status == TaskStatus.DONE:
            await task_service.reopen_ancestors(db, task.id, actor.id)
    before = {key: getattr(issue, key) for key in changes}
    for key, value in changes.items():
        setattr(issue, key, value)
    if changes.get("state") == "resolved":
        issue.resolved_at = now()
    elif changes.get("state") == "open":
        issue.resolved_at = None
    await record_change(db, task_id, actor.id, before, changes, "处理任务阻塞：" + issue.title)
    await db.flush()
    queue_project_event(db, task.project_id)
    return await task_detail(db, task_id, actor)


async def list_open_issues(db, project_ids=None):
    query = select(TaskIssue, Task.title, Project.id, Project.name, Project.owner_id, User.full_name).join(
        Task, TaskIssue.task_id == Task.id).join(Project, Task.project_id == Project.id).join(User, TaskIssue.owner_id == User.id).where(
        TaskIssue.state == "open", Task.is_deleted == False, Project.status != ProjectStatus.ARCHIVED)
    if project_ids is not None:
        query = query.where(Project.id.in_(project_ids))
    rows = (await db.execute(query.order_by(TaskIssue.due_at))).all()
    return [{**issue_out(issue, {issue.owner_id: owner_name}, escalation), "project_id": project_id,
             "task_title": task_title, "project_name": project_name}
            for issue, task_title, project_id, project_name, escalation, owner_name in rows]
