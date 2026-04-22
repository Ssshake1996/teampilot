import json
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_progress import TaskProgress
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.services import project_service, task_service
from app.services.ai.llm_client import LLMClient


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    parsed_date = _parse_date(value)
    if not parsed_date:
        return None
    return datetime.combine(parsed_date, time(hour=18), tzinfo=timezone.utc)


def _priority(value: Any) -> TaskPriority:
    try:
        return TaskPriority(str(value or "").lower())
    except ValueError:
        return TaskPriority.MEDIUM


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _active_users(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(User.id, User.full_name, User.department, User.bio)
            .where(User.is_active == True)
            .order_by(User.full_name)
        )
    ).all()
    return [
        {
            "id": str(user_id),
            "name": full_name,
            "department": department or "",
            "bio": bio or "",
        }
        for user_id, full_name, department, bio in rows
    ]


async def _project_snapshot(db: AsyncSession, include_tasks: bool = True) -> list[dict]:
    projects = (
        await db.execute(
            select(Project)
            .where(Project.status != ProjectStatus.ARCHIVED)
            .order_by(Project.created_at.desc())
        )
    ).scalars().all()

    items = []
    for project in projects:
        total = (
            await db.execute(
                select(func.count(Task.id)).where(Task.project_id == project.id, Task.is_deleted == False)
            )
        ).scalar() or 0
        done = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.project_id == project.id,
                    Task.status == TaskStatus.DONE,
                    Task.is_deleted == False,
                )
            )
        ).scalar() or 0
        item = {
            "id": str(project.id),
            "name": project.name,
            "goal": project.goal or "",
            "status": project.status.value,
            "start_date": project.start_date,
            "end_date": project.end_date,
            "task_count": total,
            "completed_count": done,
            "completion_rate": round(done / total * 100) if total else 0,
        }
        if include_tasks:
            task_rows = (
                await db.execute(
                    select(Task)
                    .where(Task.project_id == project.id, Task.is_deleted == False)
                    .order_by(Task.created_at.desc())
                    .limit(30)
                )
            ).scalars().all()
            assignee_map = await task_service.get_task_assignee_map(db, task_rows)
            item["tasks"] = [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "status": task_service.effective_task_status(task).value,
                    "progress_pct": await task_service.get_task_progress_pct(db, task),
                    "assignee": "、".join(
                        entry["full_name"] for entry in assignee_map.get(task.id, []) if entry["full_name"]
                    ),
                    "deadline": task.deadline,
                    "completed_at": task.completed_at,
                    "signed_off_at": task.signed_off_at,
                }
                for task in task_rows
            ]
        items.append(item)
    return items


async def preview_project_plan(db: AsyncSession, prompt: str, llm: LLMClient) -> dict:
    users = await _active_users(db)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior project manager. Return JSON only. "
                "{\"project\":{\"name\":\"\",\"goal\":\"\",\"description\":\"\",\"start_date\":\"YYYY-MM-DD\","
                "\"end_date\":\"YYYY-MM-DD\"},"
                "\"tasks\":[{\"title\":\"\",\"description\":\"\",\"priority\":\"medium\","
                "\"estimated_hours\":8,\"start_date\":\"YYYY-MM-DD\",\"deadline\":\"YYYY-MM-DD\","
                "\"assignee_ids\":[],\"reason\":\"\",\"children\":[]}]} "
                "priority must be low/medium/high/urgent. assignee_ids must come from team members."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "request": prompt,
                "team_members": users,
                "today": date.today().isoformat(),
            }, ensure_ascii=False, default=_json_default),
        },
    ]
    result = await llm.chat_json(messages, temperature=0.2, max_tokens=4096)
    result.setdefault("project", {})
    result["project"].setdefault("goal", prompt)
    result.setdefault("tasks", [])
    return result


async def commit_project_plan(db: AsyncSession, plan: dict, owner_id: uuid.UUID) -> dict:
    project_data = plan.get("project") or {}
    project = await project_service.create_project(
        db,
        ProjectCreate(
            name=project_data.get("name") or "AI generated project",
            goal=project_data.get("goal") or project_data.get("description") or "",
            description=project_data.get("description") or "",
            start_date=_parse_date(project_data.get("start_date")),
            end_date=_parse_date(project_data.get("end_date")),
        ),
        owner_id,
    )

    created_tasks = []

    async def create_task_item(item: dict, parent_id: uuid.UUID | None = None) -> None:
        assignee_ids: list[uuid.UUID] = []
        for raw_assignee in item.get("assignee_ids") or []:
            try:
                assignee_ids.append(uuid.UUID(str(raw_assignee)))
            except ValueError:
                continue

        task = await task_service.create_task(
            db,
            project.id,
            TaskCreate(
                title=item.get("title") or "Untitled task",
                description=item.get("description") or "",
                priority=_priority(item.get("priority")),
                assignee_ids=assignee_ids,
                parent_task_id=parent_id,
                estimated_hours=_float_or_none(item.get("estimated_hours")),
                start_date=_parse_datetime(item.get("start_date")),
                deadline=_parse_datetime(item.get("deadline")),
            ),
            owner_id,
        )
        created_tasks.append(await task_service.task_to_out(db, task))
        for child in item.get("children") or []:
            if isinstance(child, dict):
                await create_task_item(child, task.id)

    for item in plan.get("tasks") or []:
        if isinstance(item, dict):
            await create_task_item(item)

    return {
        "project": {
            **{c.name: getattr(project, c.name) for c in project.__table__.columns},
            "task_count": len(created_tasks),
            "completed_count": 0,
            "member_count": 1,
        },
        "tasks": created_tasks,
    }


def _task_line(project: dict, task: dict) -> str:
    assignee = task.get("assignee") or "unassigned"
    progress = task.get("progress_pct") or 0
    return f"{project.get('name', '')} / {task.get('title', '')} ({assignee}, {progress}%)"


def _rule_based_daily_brief(projects: list[dict], progress: list[dict], ai_error: str | None = None) -> dict:
    today = date.today()
    completed: list[str] = []
    in_progress: list[str] = []
    risks: list[str] = []
    actions: list[str] = []
    signoff_candidates: list[str] = []

    for project in projects:
        for task in project.get("tasks") or []:
            status = task.get("status")
            progress_pct = task.get("progress_pct") or 0
            line = _task_line(project, task)

            if status == TaskStatus.DONE.value:
                completed.append(line)
                continue
            if status == TaskStatus.IN_PROGRESS.value:
                in_progress.append(line)

            if progress_pct >= 100 and not task.get("signed_off_at"):
                signoff_candidates.append(line)
                risks.append(f"{line} reached 100% but is still waiting for signoff")

            deadline = _parse_date(task.get("deadline"))
            if deadline and deadline < today and status != TaskStatus.DONE.value:
                risks.append(f"{line} is overdue since {deadline.isoformat()}")

    blocked = [
        item for item in progress
        if any(word in str(item.get("note") or "") for word in ["阻塞", "卡住", "风险", "延期", "无法", "待确认"])
    ]
    for item in blocked[:10]:
        risks.append(f"{item.get('project')} / {item.get('task')} risk note: {item.get('note')}")

    if signoff_candidates:
        actions.append("Review signoff candidates first so 100% tasks can be closed automatically.")
    overdue_count = sum(1 for risk in risks if "overdue" in risk)
    if overdue_count:
        actions.append(f"Check owner, deadline, and blockers for {overdue_count} overdue tasks.")
    if blocked:
        actions.append("Follow up the progress logs that mention blockers, delays, or pending confirmation.")
    if not actions:
        actions.append("No obvious exception today. Keep collecting updates and maintain current pace.")

    summary = (
        f"Active projects: {len(projects)}. "
        f"Completed tasks: {len(completed)}. "
        f"In progress: {len(in_progress)}. "
        f"Pending signoff: {len(signoff_candidates)}. "
        f"Risks: {len(risks)}."
    )
    if ai_error:
        summary += " AI generation failed, so this brief was produced by system rules."

    return {
        "source": "rules",
        "source_label": "System rules",
        "summary": summary,
        "completed": completed[:20],
        "in_progress": in_progress[:20],
        "risks": risks[:20],
        "actions": actions[:10],
        "signoff_candidates": signoff_candidates[:20],
    }


async def daily_brief(db: AsyncSession, llm: LLMClient | None = None) -> dict:
    projects = await _project_snapshot(db, include_tasks=True)
    recent_rows = (
        await db.execute(
            select(TaskProgress, Task.title, Project.name, User.full_name)
            .join(Task, TaskProgress.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .join(User, TaskProgress.user_id == User.id)
            .where(Project.status != ProjectStatus.ARCHIVED)
            .order_by(TaskProgress.created_at.desc())
            .limit(80)
        )
    ).all()
    progress = [
        {
            "project": project_name,
            "task": task_title,
            "user": user_name,
            "progress_pct": log.progress_pct,
            "note": log.note,
            "created_at": log.created_at,
        }
        for log, task_title, project_name, user_name in recent_rows
    ]
    if not llm:
        return _rule_based_daily_brief(projects, progress)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a PMO assistant. Return JSON only with keys: "
                "summary, completed, in_progress, risks, actions, signoff_candidates. "
                "Call out overdue work, stale progress, 100% tasks still waiting for signoff, "
                "abnormal workload, and blockers mentioned in progress logs."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "projects": projects,
                "recent_progress": progress,
                "today": date.today().isoformat(),
            }, ensure_ascii=False, default=_json_default),
        },
    ]
    try:
        result = await llm.chat_json(messages, temperature=0.2, max_tokens=4096)
        result.setdefault("summary", "")
        result.setdefault("completed", [])
        result.setdefault("in_progress", [])
        result.setdefault("risks", [])
        result.setdefault("actions", [])
        result.setdefault("signoff_candidates", [])
        result["source"] = "ai"
        result["source_label"] = "AI generated"
        return result
    except Exception as exc:
        return _rule_based_daily_brief(projects, progress, f"{type(exc).__name__}: {exc}")


async def signoff_assistant(db: AsyncSession, task_id: uuid.UUID, llm: LLMClient) -> dict:
    task = await task_service.get_task(db, task_id)
    if not task:
        raise ValueError("Task not found")
    history = await task_service.get_progress_history(db, task_id)
    subtasks = await task_service.get_subtasks(db, task_id)
    context = {
        "task": await task_service.task_to_out(db, task),
        "subtasks": subtasks,
        "progress_history": history,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are a signoff assistant. Return JSON only with keys "
                "recommendation, summary, checks, risks, questions. "
                "If progress is below 100%, subtasks are unfinished, or the history still shows pending validation, return hold."
            ),
        },
        {"role": "user", "content": json.dumps(context, ensure_ascii=False, default=_json_default)},
    ]
    return await llm.chat_json(messages, temperature=0.1, max_tokens=2048)


async def project_retrospective(db: AsyncSession, project_id: uuid.UUID, llm: LLMClient) -> dict:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")
    tasks = await project_service.get_project_task_tree(db, project_id)
    progress_rows = (
        await db.execute(
            select(TaskProgress, Task.title, User.full_name)
            .join(Task, TaskProgress.task_id == Task.id)
            .join(User, TaskProgress.user_id == User.id)
            .where(Task.project_id == project_id)
            .order_by(TaskProgress.created_at.desc())
            .limit(120)
        )
    ).all()
    progress = [
        {
            "task": title,
            "user": name,
            "progress_pct": log.progress_pct,
            "note": log.note,
            "created_at": log.created_at,
        }
        for log, title, name in progress_rows
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You are a retrospective analyst. Return JSON only with keys "
                "summary, wins, issues, estimation_lessons, process_improvements, reusable_template."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "project": {
                    "name": project.name,
                    "goal": project.goal,
                    "description": project.description,
                    "status": project.status.value,
                    "start_date": project.start_date,
                    "end_date": project.end_date,
                },
                "tasks": tasks,
                "progress": progress,
            }, ensure_ascii=False, default=_json_default),
        },
    ]
    return await llm.chat_json(messages, temperature=0.2, max_tokens=4096)
