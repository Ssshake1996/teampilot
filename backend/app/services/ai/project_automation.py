import json
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.services import project_service, task_service
from app.services.ai.errors import AIBackendError
from app.services.ai.llm_client import LLMClient
from app.services.report_metrics import progress_rankings


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _local_today() -> date:
    try:
        tz = ZoneInfo(settings.REPORT_TIMEZONE)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date()


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
                    "goal": task.goal or "",
                    "status": task_service.effective_task_status(task).value,
                    "progress_pct": await task_service.get_task_progress_pct(db, task),
                    "assignee": ", ".join(
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
                "\"tasks\":[{\"title\":\"\",\"goal\":\"\",\"description\":\"\",\"priority\":\"medium\","
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
                "today": _local_today().isoformat(),
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
                goal=item.get("goal") or "",
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


INSPECTION_REPORT_FIELDS = [
    "summary",
    "risky_projects",
    "overdue_blocked_tasks",
    "progress_fast_top3",
    "progress_slow_top3",
    "priority_tasks",
    "signoff_pending",
]

INSPECTION_REPORT_DEFAULTS = {
    "summary": "当前没有生成有效摘要。",
    "risky_projects": ["今天没有发现明显的项目级风险。"],
    "overdue_blocked_tasks": ["今天没有逾期或明显阻塞的任务。"],
    "progress_fast_top3": ["今天没有足够数据判断进展较快成员。"],
    "progress_slow_top3": ["今天没有足够数据判断进展较慢成员。"],
    "priority_tasks": ["今天没有需要额外优先处理的任务。"],
    "signoff_pending": ["今天没有达到 100% 但待会签的任务。"],
}


def _as_string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return default.copy()
    if isinstance(value, list):
        items = [
            item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=_json_default)
            for item in value
            if item not in (None, "")
        ]
    elif isinstance(value, str):
        items = [value] if value.strip() else []
    else:
        items = [json.dumps(value, ensure_ascii=False, default=_json_default)]
    return items[:20] or default.copy()


def normalize_inspection_report(report: dict | None, source: str, source_label: str) -> dict:
    raw = report or {}
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = INSPECTION_REPORT_DEFAULTS["summary"]

    normalized = {
        "summary": summary.strip(),
        "risky_projects": _as_string_list(raw.get("risky_projects"), INSPECTION_REPORT_DEFAULTS["risky_projects"]),
        "overdue_blocked_tasks": _as_string_list(
            raw.get("overdue_blocked_tasks"),
            INSPECTION_REPORT_DEFAULTS["overdue_blocked_tasks"],
        ),
        "progress_fast_top3": _as_string_list(
            raw.get("progress_fast_top3"),
            INSPECTION_REPORT_DEFAULTS["progress_fast_top3"],
        ),
        "progress_slow_top3": _as_string_list(
            raw.get("progress_slow_top3"),
            INSPECTION_REPORT_DEFAULTS["progress_slow_top3"],
        ),
        "priority_tasks": _as_string_list(raw.get("priority_tasks"), INSPECTION_REPORT_DEFAULTS["priority_tasks"]),
        "signoff_pending": _as_string_list(raw.get("signoff_pending"), INSPECTION_REPORT_DEFAULTS["signoff_pending"]),
        "source": source,
        "source_label": source_label,
    }
    return normalized


def _rule_based_inspection_report(
    projects: list[dict],
    progress: list[dict],
    members: list[dict],
    ai_error: str | None = None,
) -> dict:
    today = _local_today()
    blocked_keywords = ("阻塞", "卡住", "风险", "延期", "无法", "待确认", "依赖")
    risky_projects: list[str] = []
    overdue_blocked_tasks: list[str] = []
    priority_tasks: list[str] = []
    signoff_pending: list[str] = []
    risky_project_names: set[str] = set()

    for item in progress:
        created_at = item.get("created_at")
        created_date = created_at.date() if isinstance(created_at, datetime) else _parse_date(created_at)
        if created_date != today:
            continue

        note = str(item.get("note") or "")
        if note and any(keyword in note for keyword in blocked_keywords):
            overdue_blocked_tasks.append(f"{item.get('project')} / {item.get('task')}: {note}")
            project_name = str(item.get("project") or "未命名项目")
            if project_name not in risky_project_names:
                risky_projects.append(f"{project_name}：存在阻塞或待确认进展")
                risky_project_names.add(project_name)

    for project in projects:
        project_name = project.get("name") or "未命名项目"
        project_overdue = 0
        project_signoff = 0

        for task in project.get("tasks") or []:
            status = task.get("status")
            progress_pct = task.get("progress_pct") or 0
            line = _task_line(project, task)

            if progress_pct >= 100 and not task.get("signed_off_at"):
                project_signoff += 1
                signoff_pending.append(f"{line} 已达 100% 但仍待会签")

            deadline = _parse_date(task.get("deadline"))
            if deadline and deadline < today and status != TaskStatus.DONE.value:
                project_overdue += 1
                overdue_blocked_tasks.append(f"{line} 已逾期，截止日期 {deadline.isoformat()}")

            if deadline and status != TaskStatus.DONE.value:
                days_left = (deadline - today).days
                if days_left <= 2 and progress_pct < 70:
                    priority_tasks.append(f"{line} 临近截止且当前进度 {progress_pct}%")
                elif status == TaskStatus.NOT_STARTED.value and days_left <= 3:
                    priority_tasks.append(f"{line} 尚未开始且距离截止仅剩 {days_left} 天")

        if project_overdue or project_signoff:
            summary_bits: list[str] = []
            if project_overdue:
                summary_bits.append(f"{project_overdue} 项任务逾期")
            if project_signoff:
                summary_bits.append(f"{project_signoff} 项任务待会签")
            risky_projects.append(f"{project_name}：{'，'.join(summary_bits)}")
            risky_project_names.add(project_name)

    progress_fast_top3, progress_slow_top3 = progress_rankings(
        projects,
        progress,
        today,
        today,
        INSPECTION_REPORT_DEFAULTS["progress_fast_top3"][0],
        INSPECTION_REPORT_DEFAULTS["progress_slow_top3"][0],
    )

    if not risky_projects:
        risky_projects.append("今天没有发现明显的项目级风险。")
    if not overdue_blocked_tasks:
        overdue_blocked_tasks.append("今天没有逾期或明显阻塞的任务。")
    if not priority_tasks:
        priority_tasks.append("今天没有需要额外优先处理的任务。")
    if not signoff_pending:
        signoff_pending.append("今天没有达到 100% 但待会签的任务。")

    summary = (
        f"今日覆盖 {len(projects)} 个活跃项目，"
        f"识别出 {sum(1 for item in risky_projects if '没有发现' not in item)} 个风险项目，"
        f"{sum(1 for item in overdue_blocked_tasks if '没有逾期' not in item)} 条逾期或阻塞任务，"
        f"{sum(1 for item in signoff_pending if '没有达到' not in item)} 条待会签任务。"
    )
    if ai_error:
        summary += " AI 生成失败，当前结果由系统规则生成。"

    return normalize_inspection_report({
        "summary": summary,
        "risky_projects": risky_projects[:20],
        "overdue_blocked_tasks": overdue_blocked_tasks[:20],
        "progress_fast_top3": progress_fast_top3,
        "progress_slow_top3": progress_slow_top3,
        "priority_tasks": priority_tasks[:20],
        "signoff_pending": signoff_pending[:20],
    }, "rules", "系统规则巡检")


async def daily_brief(
    db: AsyncSession,
    llm: LLMClient | None = None,
    raise_ai_error: bool = False,
) -> dict:
    projects = await _project_snapshot(db, include_tasks=True)
    active_users = await _active_users(db)
    recent_rows = (
        await db.execute(
            select(TaskEvent, Task.title, Project.name, User.full_name)
            .join(Task, TaskEvent.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .join(User, TaskEvent.actor_id == User.id)
            .where(
                Project.status != ProjectStatus.ARCHIVED,
                TaskEvent.event_type == TaskEventType.PROGRESS,
            )
            .order_by(TaskEvent.created_at.desc())
            .limit(120)
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
        return _rule_based_inspection_report(projects, progress, active_users)

    messages = [
        {
            "role": "system",
            "content": (
                "你是项目管理办公室的巡检报告助手。"
                "只返回 JSON 对象，不要输出 markdown 或解释文字。"
                "JSON 必须且只能包含这些键：summary, risky_projects, overdue_blocked_tasks, "
                "progress_fast_top3, progress_slow_top3, priority_tasks, signoff_pending。"
                "summary 必须是一个简洁中文字符串。"
                "其余六个字段必须是中文字符串数组；没有结果时也返回一句“没有发现...”类结论，不要返回空数组。"
                "progress_fast_top3 和 progress_slow_top3 必须各最多 3 条。"
                "不要修改任何任务数据。"
                "请基于输入给出简洁、准确、完整、可执行的中文结论。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "projects": projects,
                "team_members": active_users,
                "recent_progress": progress,
                "today": _local_today().isoformat(),
            }, ensure_ascii=False, default=_json_default),
        },
    ]
    try:
        result = await llm.chat_json(messages, temperature=0.2, max_tokens=4096)
        return normalize_inspection_report(result, "ai", "AI 生成")
    except Exception as exc:
        if raise_ai_error:
            raise AIBackendError("AI 生成巡检报告失败", exc) from exc
        return _rule_based_inspection_report(projects, progress, active_users, f"{type(exc).__name__}: {exc}")


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
            select(TaskEvent, Task.title, User.full_name)
            .join(Task, TaskEvent.task_id == Task.id)
            .join(User, TaskEvent.actor_id == User.id)
            .where(
                Task.project_id == project_id,
                TaskEvent.event_type == TaskEventType.PROGRESS,
            )
            .order_by(TaskEvent.created_at.desc())
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
