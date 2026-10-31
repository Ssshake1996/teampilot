import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.services import project_service, task_service
from app.services.report_metrics import progress_rankings




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
                )
            ).scalars().all()
            assignee_map = await task_service.get_task_assignee_map(db, task_rows)
            progress_map = await task_service.get_project_task_progress_map(db, project.id, task_rows)
            item["tasks"] = [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "goal": task.goal or "",
                    "status": task_service.effective_task_status(task).value,
                    "progress_pct": progress_map.get(task.id, 0),
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
            item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str)
            for item in value
            if item not in (None, "")
        ]
    elif isinstance(value, str):
        items = [value] if value.strip() else []
    else:
        items = [json.dumps(value, ensure_ascii=False, default=str)]
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
    return _rule_based_inspection_report(projects, progress, active_users)
