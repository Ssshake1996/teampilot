import json
import smtplib
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.services import task_service


REPORT_SECTIONS = [
    ("risky_projects", "风险项目"),
    ("overdue_blocked_tasks", "逾期 / 阻塞任务"),
    ("members_without_updates", "未更新成员"),
    ("priority_tasks", "优先推进任务"),
    ("signoff_pending", "待会签任务"),
    ("completed_tasks", "已会签完成"),
    ("progress_updates", "进展记录"),
]


def parse_recipients(values: list[str] | str | None) -> list[str]:
    if values is None:
        raw = settings.REPORT_DEFAULT_RECIPIENTS
    elif isinstance(values, str):
        raw = values
    elif not values:
        raw = settings.REPORT_DEFAULT_RECIPIENTS
    else:
        raw = ",".join(values)

    recipients: list[str] = []
    seen: set[str] = set()
    for item in raw.replace(";", ",").replace("\n", ",").split(","):
        email = item.strip()
        if email and email not in seen:
            seen.add(email)
            recipients.append(email)
    return recipients


def _stringify_item(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def report_subject(report_type: str, report: dict) -> str:
    if report_type == "weekly":
        start = report.get("period_start")
        end = report.get("period_end")
        suffix = f"{start} 至 {end}" if start and end else date.today().isoformat()
        return f"[TeamPilot] 周报 {suffix}"
    return f"[TeamPilot] 巡检报告 {date.today().isoformat()}"


def format_report_text(report_type: str, report: dict) -> str:
    title = "TeamPilot 周报" if report_type == "weekly" else "TeamPilot 巡检报告"
    lines = [title]
    if report_type == "weekly":
        lines.append(f"周期：{report.get('period_start', '-')} 至 {report.get('period_end', '-')}")
    lines.extend(["", "摘要", str(report.get("summary") or "暂无摘要"), ""])

    for key, label in REPORT_SECTIONS:
        items = report.get(key)
        if not items:
            continue
        lines.append(label)
        if isinstance(items, list):
            lines.extend(f"- {_stringify_item(item)}" for item in items)
        else:
            lines.append(f"- {_stringify_item(items)}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def send_report_email(recipients: list[str], subject: str, body: str) -> None:
    if not settings.SMTP_HOST:
        raise ValueError("SMTP_HOST is not configured.")
    if not recipients:
        raise ValueError("No report recipients configured.")

    sender = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    if not sender:
        raise ValueError("SMTP_FROM_EMAIL or SMTP_USERNAME is required.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    smtp_cls = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def _date_value(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


async def generate_weekly_report(db: AsyncSession) -> dict:
    today = date.today()
    period_start = today - timedelta(days=6)
    start_dt = datetime.combine(period_start, time.min)
    end_dt = datetime.combine(today, time.max)
    projects = (
        await db.execute(
            select(Project)
            .where(Project.status != ProjectStatus.ARCHIVED)
            .order_by(Project.created_at.desc())
        )
    ).scalars().all()
    active_users = (
        await db.execute(select(User).where(User.is_active == True).order_by(User.full_name))
    ).scalars().all()

    risky_projects: list[str] = []
    overdue_blocked_tasks: list[str] = []
    priority_tasks: list[str] = []
    signoff_pending: list[str] = []

    for project in projects:
        tasks = (
            await db.execute(
                select(Task)
                .where(Task.project_id == project.id, Task.is_deleted == False)
                .order_by(Task.sort_order, Task.created_at)
            )
        ).scalars().all()
        assignee_map = await task_service.get_task_assignee_map(db, tasks)
        project_overdue = 0
        project_signoff = 0
        project_priority = 0

        for task in tasks:
            status = task_service.effective_task_status(task)
            progress_pct = await task_service.get_task_progress_pct(db, task)
            assignees = "、".join(
                entry["full_name"] for entry in assignee_map.get(task.id, []) if entry["full_name"]
            ) or "未分配"
            line = f"{project.name} / {task.title} ({assignees}, {progress_pct}%)"
            deadline = _date_value(task.deadline)

            if progress_pct >= 100 and status != TaskStatus.DONE and not task.signed_off_at:
                project_signoff += 1
                signoff_pending.append(f"{line} 已达到 100%，待会签确认")

            if deadline and deadline < today and status != TaskStatus.DONE:
                project_overdue += 1
                overdue_blocked_tasks.append(f"{line} 已逾期，截止日期 {deadline.isoformat()}")

            if status != TaskStatus.DONE:
                due_soon = deadline is not None and (deadline - today).days <= 7
                high_priority = task.priority in (TaskPriority.HIGH, TaskPriority.URGENT)
                if due_soon or high_priority:
                    project_priority += 1
                    reason = "高优先级" if high_priority else "临近截止"
                    priority_tasks.append(f"{line} {reason}")

        if project_overdue or project_signoff or project_priority:
            bits: list[str] = []
            if project_overdue:
                bits.append(f"{project_overdue} 项逾期")
            if project_signoff:
                bits.append(f"{project_signoff} 项待会签")
            if project_priority:
                bits.append(f"{project_priority} 项需优先推进")
            risky_projects.append(f"{project.name}：{'，'.join(bits)}")

    progress_rows = (
        await db.execute(
            select(TaskEvent, Task.title, Project.name, User.full_name)
            .join(Task, TaskEvent.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .join(User, TaskEvent.actor_id == User.id)
            .where(
                Project.status != ProjectStatus.ARCHIVED,
                TaskEvent.event_type == TaskEventType.PROGRESS,
                TaskEvent.created_at >= start_dt,
                TaskEvent.created_at <= end_dt,
            )
            .order_by(TaskEvent.created_at.desc())
            .limit(80)
        )
    ).all()
    updated_members = {user_name for _, _, _, user_name in progress_rows if user_name}
    progress_updates = [
        f"{created_at.created_at.strftime('%Y-%m-%d')} {user_name}：{project_name} / {task_title} {created_at.progress_pct}%"
        + (f" - {created_at.note}" if created_at.note else "")
        for created_at, task_title, project_name, user_name in progress_rows[:30]
    ]

    completed_rows = (
        await db.execute(
            select(TaskEvent, Task.title, Project.name, User.full_name)
            .join(Task, TaskEvent.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .join(User, TaskEvent.actor_id == User.id)
            .where(
                Project.status != ProjectStatus.ARCHIVED,
                TaskEvent.event_type == TaskEventType.SIGNOFF,
                TaskEvent.created_at >= start_dt,
                TaskEvent.created_at <= end_dt,
            )
            .order_by(TaskEvent.created_at.desc())
            .limit(50)
        )
    ).all()
    completed_tasks = [
        f"{log.created_at.strftime('%Y-%m-%d')} {project_name} / {task_title}，会签人：{user_name}"
        for log, task_title, project_name, user_name in completed_rows
    ]

    members_without_updates = [
        user.full_name for user in active_users if user.full_name not in updated_members
    ]

    if not risky_projects:
        risky_projects.append("本周没有发现明显的项目级风险。")
    if not overdue_blocked_tasks:
        overdue_blocked_tasks.append("本周没有发现逾期或明显阻塞的任务。")
    if not priority_tasks:
        priority_tasks.append("本周没有需要额外优先推进的任务。")
    if not signoff_pending:
        signoff_pending.append("本周没有达到 100% 但待会签的任务。")
    if not completed_tasks:
        completed_tasks.append("本周没有会签完成的任务。")
    if not progress_updates:
        progress_updates.append("本周没有进展记录。")
    if not members_without_updates:
        members_without_updates.append("本周所有活跃成员都有进展记录。")

    summary = (
        f"本周覆盖 {len(projects)} 个未归档项目，"
        f"{len(progress_rows)} 条进展记录，"
        f"{len(completed_rows)} 项会签完成，"
        f"{sum(1 for item in risky_projects if '没有发现' not in item)} 个项目需要关注。"
    )

    return {
        "source": "rules",
        "source_label": "系统周报",
        "period_start": period_start.isoformat(),
        "period_end": today.isoformat(),
        "summary": summary,
        "risky_projects": risky_projects[:20],
        "overdue_blocked_tasks": overdue_blocked_tasks[:20],
        "members_without_updates": members_without_updates[:30],
        "priority_tasks": priority_tasks[:20],
        "signoff_pending": signoff_pending[:20],
        "completed_tasks": completed_tasks[:20],
        "progress_updates": progress_updates[:30],
    }
