from app.services.inspection_service import daily_brief
import asyncio
import json
import smtplib
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from typing import Any
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.models.system_setting import SystemSetting
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.models.team_planning import ReportVersion
from app.services import task_service
from app.services.report_metrics import progress_rankings


REPORT_SECTIONS = [
    ("project_progress_table", "项目进展情况表"),
    ("risky_projects", "风险项目"),
    ("overdue_blocked_tasks", "逾期 / 阻塞任务"),
    ("progress_fast_top3", "本期已验收成果"),
    ("progress_slow_top3", "需支持事项"),
    ("priority_tasks", "优先推进任务"),
    ("signoff_pending", "待会签任务"),
    ("completed_tasks", "已会签完成"),
    ("progress_updates", "进展记录"),
    ("commitments", "本周承诺"),
    ("deviations", "承诺偏差"),
    ("next_steps", "下一步与改进行动"),
]

REPORT_SNAPSHOT_KEYS = {
    "daily": "report_snapshot_daily",
    "weekly": "report_snapshot_weekly",
}




def _report_tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.REPORT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(_report_tz())


def _today() -> date:
    return _now().date()


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
        suffix = f"{start} 至 {end}" if start and end else _today().isoformat()
        return f"[TeamPilot] 周报 {suffix}"
    return f"[TeamPilot] 巡检报告 {_today().isoformat()}"


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
        if key == "project_progress_table" and isinstance(items, list):
            lines.append("项目 | 总进度 | 本周进展 | 任务完成 | 逾期任务 | 风险等级 | 下周建议")
            lines.append("--- | --- | --- | --- | --- | --- | ---")
            for item in items:
                if not isinstance(item, dict):
                    lines.append(f"- {_stringify_item(item)}")
                    continue
                lines.append(
                    f"{item.get('project_name', '-')} | "
                    f"{item.get('progress_pct', 0)}% | "
                    f"{item.get('weekly_progress', '-')} | "
                    f"{item.get('task_completion', '-')} | "
                    f"{item.get('overdue_tasks', 0)} | "
                    f"{item.get('risk_level', '-')} | "
                    f"{item.get('next_action', '-')}"
                )
            lines.append("")
            continue
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


async def generate_weekly_report(
    db: AsyncSession,
    project_ids=None,
) -> dict:
    today = _today()
    period_start = today - timedelta(days=today.weekday())
    start_dt = datetime.combine(period_start, time.min)
    end_dt = datetime.combine(today, time.max)
    projects = (
        await db.execute(
            select(Project)
            .where(Project.status != ProjectStatus.ARCHIVED, *([Project.id.in_(project_ids)] if project_ids is not None else []))
            .order_by(Project.created_at.desc())
        )
    ).scalars().all()

    project_snapshots: list[dict] = []
    project_progress_table: list[dict] = []
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
        total_tasks = len(tasks)
        done_tasks = 0
        in_progress_tasks = 0
        project_overdue = 0
        project_signoff = 0
        project_priority = 0
        week_deliveries = 0
        task_items: list[dict] = []

        for task in tasks:
            status = task_service.effective_task_status(task)
            progress_pct = await task_service.get_task_progress_pct(db, task)
            if status == TaskStatus.DONE:
                done_tasks += 1
                if task.signed_off_at and period_start <= task.signed_off_at.date() <= today:
                    week_deliveries += 1
            elif status == TaskStatus.IN_PROGRESS:
                in_progress_tasks += 1
            assignees = "、".join(
                entry["full_name"] for entry in assignee_map.get(task.id, []) if entry["full_name"]
            ) or "未分配"
            line = f"{project.name} / {task.title} ({assignees}, {progress_pct}%)"
            deadline = _date_value(task.deadline)
            task_items.append({
                "id": str(task.id),
                "title": task.title,
                "status": status.value,
                "progress_pct": progress_pct,
                "assignee": assignees,
                "deadline": task.deadline,
                "signed_off_at": task.signed_off_at,
            })

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

        week_update_count = (
            await db.execute(
                select(func.count(TaskEvent.id))
                .join(Task, TaskEvent.task_id == Task.id)
                .where(
                    Task.project_id == project.id,
                    TaskEvent.event_type == TaskEventType.PROGRESS,
                    TaskEvent.created_at >= start_dt,
                    TaskEvent.created_at <= end_dt,
                )
            )
        ).scalar() or 0
        progress_pct = round(done_tasks / total_tasks * 100) if total_tasks else 0
        if project_overdue:
            risk_level = "高"
            next_action = "先处理逾期任务，明确阻塞原因和负责人。"
        elif project_signoff:
            risk_level = "中"
            next_action = "优先完成 100% 任务会签，关闭已达成事项。"
        elif project_priority:
            risk_level = "中"
            next_action = "推进高优先级或临近截止任务。"
        else:
            risk_level = "低"
            next_action = "按当前计划推进。"

        project_progress_table.append({
            "project_name": project.name,
            "status": project.status.value,
            "progress_pct": progress_pct,
            "weekly_progress": f"本周验收交付 {week_deliveries} 项；{week_update_count} 条进展记录（不计个人评分）",
            "weekly_delivered_count": week_deliveries,
            "task_completion": f"{done_tasks}/{total_tasks}",
            "overdue_tasks": project_overdue,
            "risk_level": risk_level,
            "next_action": next_action,
        })
        project_snapshots.append({
            "id": str(project.id),
            "name": project.name,
            "status": project.status.value,
            "tasks": task_items,
        })

    progress_rows = (
        await db.execute(
            select(TaskEvent, Task.title, Project.name, User.full_name)
            .join(Task, TaskEvent.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .join(User, TaskEvent.actor_id == User.id)
            .where(
                Project.status != ProjectStatus.ARCHIVED,
                TaskEvent.event_type == TaskEventType.PROGRESS,
                *([Project.id.in_(project_ids)] if project_ids is not None else []),
                TaskEvent.created_at >= start_dt,
                TaskEvent.created_at <= end_dt,
            )
            .order_by(TaskEvent.created_at.desc())
            .limit(80)
        )
    ).all()
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
                *([Project.id.in_(project_ids)] if project_ids is not None else []),
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

    progress_for_rankings = [
        {
            "project": project_name,
            "task": task_title,
            "user": user_name,
            "progress_pct": log.progress_pct,
            "note": log.note,
            "created_at": log.created_at,
        }
        for log, task_title, project_name, user_name in progress_rows
    ]
    progress_fast_top3, progress_slow_top3 = progress_rankings(
        project_snapshots,
        progress_for_rankings,
        period_start,
        today,
        "本周没有足够数据判断进展较快成员。",
        "本周没有足够数据判断进展较慢成员。",
    )

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

    summary = (
        f"本周覆盖 {len(projects)} 个未归档项目，"
        f"{len(progress_rows)} 条进展记录，"
        f"{len(completed_rows)} 项会签完成，"
        f"{sum(1 for item in risky_projects if '没有发现' not in item)} 个项目需要关注。"
    )

    rule_report = {
        "source": "rules",
        "source_label": "系统周报",
        "period_start": period_start.isoformat(),
        "period_end": today.isoformat(),
        "summary": summary,
        "project_progress_table": project_progress_table,
        "risky_projects": risky_projects[:20],
        "overdue_blocked_tasks": overdue_blocked_tasks[:20],
        "progress_fast_top3": progress_fast_top3,
        "progress_slow_top3": progress_slow_top3,
        "priority_tasks": priority_tasks[:20],
        "signoff_pending": signoff_pending[:20],
        "completed_tasks": completed_tasks[:20],
        "progress_updates": progress_updates[:30],
    }

    from app.services.task_management_service import list_open_issues
    from app.services.team_planning_service import weekly_outcomes
    active_project_ids = [project.id for project in projects]
    issues = await list_open_issues(db, active_project_ids)
    if issues:
        lines = [f"{item['project_name']} / {item['task_title']}：{item['title']}；处理人 {item['owner_name']}；下一步 {item['next_action']}" + ("（已超期，需项目负责人协调）" if item['is_overdue'] else "") for item in issues]
        rule_report["overdue_blocked_tasks"] = lines + [line for line in rule_report["overdue_blocked_tasks"] if "没有发现" not in line]
        rule_report["progress_slow_top3"] = lines + [line for line in rule_report["progress_slow_top3"] if "暂无明确" not in line]
        rule_report["risky_projects"] = list(dict.fromkeys([f"{item['project_name']}：存在未解除阻塞" for item in issues] + [line for line in rule_report["risky_projects"] if "没有发现" not in line]))
    rule_report["support_needed"] = rule_report["progress_slow_top3"]
    rule_report["delivered"] = rule_report["progress_fast_top3"]
    rule_report["project_ids"] = [str(project.id) for project in projects]
    outcomes = await weekly_outcomes(db, period_start, today, active_project_ids)
    rule_report.update({key: value for key, value in outcomes.items() if key != "delivered"})
    return rule_report


def _snapshot_key(report_type: str) -> str:
    if report_type not in REPORT_SNAPSHOT_KEYS:
        raise ValueError(f"Unsupported report type: {report_type}")
    return REPORT_SNAPSHOT_KEYS[report_type]


def _scheduled_time(report_type: str, now: datetime | None = None) -> datetime:
    current = now or _now()
    if report_type == "daily":
        return current.replace(hour=7, minute=0, second=0, microsecond=0)
    if report_type == "weekly":
        friday = current.date() + timedelta(days=(4 - current.weekday()))
        return current.replace(
            year=friday.year,
            month=friday.month,
            day=friday.day,
            hour=12,
            minute=30,
            second=0,
            microsecond=0,
        )
    raise ValueError(f"Unsupported report type: {report_type}")


def _schedule_key(report_type: str, now: datetime | None = None) -> str:
    current = now or _now()
    scheduled = _scheduled_time(report_type, current)
    if current < scheduled:
        scheduled = scheduled - (timedelta(days=1) if report_type == "daily" else timedelta(days=7))
    return f"{report_type}:{scheduled.isoformat(timespec='minutes')}"


def _is_schedule_due(report_type: str, now: datetime | None = None) -> bool:
    current = now or _now()
    return current >= _scheduled_time(report_type, current)




async def generate_report_payload(
    db: AsyncSession,
    report_type: str,
    project_ids=None,
) -> dict:
    if report_type == "daily":
        return await daily_brief(db, project_ids=project_ids)
    if report_type == "weekly":
        return await generate_weekly_report(db, project_ids=project_ids)
    raise ValueError(f"Unsupported report type: {report_type}")


def _audience_id(user: User | None):
    return user.id if user and user.role != "admin" else None


def _audience_key(report_type: str, user: User | None):
    key = _snapshot_key(report_type)
    return key + ":" + str(user.id) if _audience_id(user) else key


async def _scope_allowed(db: AsyncSession, report: dict, user: User | None) -> bool:
    if user is None or user.role == "admin":
        return True
    from app.services.project_access_service import get_visible_project_ids
    visible = {str(value) for value in await get_visible_project_ids(db, user)}
    ids = report.get("project_ids")
    return isinstance(ids, list) and set(ids).issubset(visible)


async def get_report_snapshot(db: AsyncSession, report_type: str, user: User | None = None) -> dict:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == _audience_key(report_type, user)))
    ).scalar_one_or_none()
    if not setting or not setting.value_json or not await _scope_allowed(db, setting.value_json.get("report") or {}, user):
        return {
            "report_type": report_type,
            "report": None,
            "generated_at": None,
            "schedule_key": None,
            "trigger": None,
        }
    return setting.value_json


async def save_report_snapshot(
    db: AsyncSession,
    report_type: str,
    report: dict,
    trigger: str,
    now: datetime | None = None,
    user: User | None = None,
) -> dict:
    current = now or _now()
    payload = {
        "report_type": report_type,
        "report": jsonable_encoder(report),
        "generated_at": current.isoformat(timespec="seconds"),
        "schedule_key": _schedule_key(report_type, current),
        "trigger": trigger,
    }
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == _audience_key(report_type, user)))
    ).scalar_one_or_none()
    if setting and setting.value_json.get("report") and not setting.value_json.get("history_id"):
        legacy = setting.value_json
        try:
            legacy_time = datetime.fromisoformat(legacy.get("generated_at", ""))
        except (ValueError, TypeError):
            legacy_time = current
        db.add(ReportVersion(report_type=report_type, report_json=legacy["report"], generated_at=legacy_time,
                             audience_user_id=_audience_id(user)))
    version = ReportVersion(report_type=report_type, report_json=payload["report"], generated_at=current,
                            audience_user_id=_audience_id(user))
    db.add(version)
    await db.flush()
    payload["history_id"] = str(version.id)
    if setting:
        setting.value_json = dict(payload)
    else:
        db.add(SystemSetting(key=_audience_key(report_type, user), value_json=dict(payload)))
    await db.flush()
    return payload


async def refresh_report_snapshot(
    db: AsyncSession,
    report_type: str,
    trigger: str = "manual",
    now: datetime | None = None,
    user: User | None = None,
) -> dict:
    from app.services.project_access_service import get_visible_project_ids
    project_ids = await get_visible_project_ids(db, user) if user else None
    report = await generate_report_payload(db, report_type, project_ids=project_ids)
    return await save_report_snapshot(db, report_type, report, trigger, now, user=user)


async def report_history(db: AsyncSession, report_type: str, user: User) -> list[dict]:
    query = select(ReportVersion).where(ReportVersion.report_type == report_type)
    if user.role != "admin":
        query = query.where(ReportVersion.audience_user_id == user.id)
    rows = (await db.execute(query.order_by(ReportVersion.generated_at.desc(), ReportVersion.id.desc()).limit(100))).scalars().all()
    return [{"id": row.id, "report_type": row.report_type, "generated_at": row.generated_at,
             "summary": row.report_json.get("summary", "")} for row in rows if await _scope_allowed(db, row.report_json, user)]


async def report_history_item(db: AsyncSession, version_id: uuid.UUID, user: User) -> dict | None:
    row = await db.get(ReportVersion, version_id)
    if row is None or (user.role != "admin" and row.audience_user_id != user.id):
        return None
    if not await _scope_allowed(db, row.report_json, user):
        return None
    return {"id": row.id, "report_type": row.report_type, "generated_at": row.generated_at, "report": row.report_json}


async def refresh_due_report(db: AsyncSession, report_type: str, now: datetime | None = None) -> bool:
    current = now or _now()
    if not _is_schedule_due(report_type, current):
        return False
    snapshot = await get_report_snapshot(db, report_type)
    if snapshot.get("schedule_key") == _schedule_key(report_type, current):
        return False
    await refresh_report_snapshot(db, report_type, trigger="schedule", now=current)
    return True


async def report_scheduler_loop(interval_seconds: int = 60) -> None:
    from app.database import async_session

    while True:
        try:
            async with async_session() as db:
                for report_type in ("daily", "weekly"):
                    await refresh_due_report(db, report_type)
                await db.commit()
        except Exception as exc:
            print(f"[WARN] report scheduler failed: {type(exc).__name__}: {exc}")
        await asyncio.sleep(interval_seconds)
