import asyncio
import json
import smtplib
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project, ProjectStatus
from app.models.system_setting import SystemSetting
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User
from app.services import task_service
from app.services.ai.llm_client import LLMClient
from app.services.ai.project_automation import daily_brief
from app.services.report_metrics import progress_rankings


REPORT_SECTIONS = [
    ("project_progress_table", "项目进展情况表"),
    ("risky_projects", "风险项目"),
    ("overdue_blocked_tasks", "逾期 / 阻塞任务"),
    ("progress_fast_top3", "进展快 TOP3"),
    ("progress_slow_top3", "进展慢 TOP3"),
    ("priority_tasks", "优先推进任务"),
    ("signoff_pending", "待会签任务"),
    ("completed_tasks", "已会签完成"),
    ("progress_updates", "进展记录"),
]

REPORT_SNAPSHOT_KEYS = {
    "daily": "report_snapshot_daily",
    "weekly": "report_snapshot_weekly",
}

AI_CONFIG_KEY = "ai_config"

WEEKLY_AI_FIELDS = [
    "risky_projects",
    "overdue_blocked_tasks",
    "progress_fast_top3",
    "progress_slow_top3",
    "priority_tasks",
    "signoff_pending",
    "completed_tasks",
    "progress_updates",
]


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


def _as_string_list(value: Any, fallback: list[str]) -> list[str]:
    if value is None:
        return fallback[:]
    if isinstance(value, list):
        rows = [_stringify_item(item).strip() for item in value if _stringify_item(item).strip()]
        return rows or fallback[:]
    text = str(value).strip()
    return [text] if text else fallback[:]


def _normalize_weekly_ai_report(raw: dict | None, fallback: dict) -> dict:
    source = raw or {}
    report = dict(fallback)
    report["source"] = "ai"
    report["source_label"] = "AI 生成"
    summary = str(source.get("summary") or "").strip()
    if summary:
        report["summary"] = summary
    for key in WEEKLY_AI_FIELDS:
        report[key] = _as_string_list(source.get(key), fallback.get(key) or [])
    return report


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


async def generate_weekly_report(db: AsyncSession, llm: LLMClient | None = None) -> dict:
    today = _today()
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
        task_items: list[dict] = []

        for task in tasks:
            status = task_service.effective_task_status(task)
            progress_pct = await task_service.get_task_progress_pct(db, task)
            if status == TaskStatus.DONE:
                done_tasks += 1
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
            "weekly_progress": f"{week_update_count} 条进展",
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

    if not llm:
        return rule_report

    messages = [
        {
            "role": "system",
            "content": (
                "你是项目管理办公室的周报助手。只返回 JSON 对象，不要输出 markdown 或解释文字。"
                "JSON 必须且只能包含这些键：summary, risky_projects, overdue_blocked_tasks, "
                "progress_fast_top3, progress_slow_top3, priority_tasks, signoff_pending, "
                "completed_tasks, progress_updates。summary 必须是简洁中文字符串。"
                "其余字段必须是中文字符串数组；没有结果时也返回一句明确结论，不要返回空数组。"
                "progress_fast_top3 和 progress_slow_top3 必须各最多 3 条。"
                "项目进展情况表由系统生成，你不要返回 project_progress_table，也不要增删项目。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "period_start": period_start.isoformat(),
                    "period_end": today.isoformat(),
                    "project_progress_table": project_progress_table,
                    "rule_findings": {
                        key: rule_report[key]
                        for key in WEEKLY_AI_FIELDS
                    },
                },
                ensure_ascii=False,
                default=str,
            ),
        },
    ]
    try:
        ai_report = await llm.chat_json(messages, temperature=0.2, max_tokens=4096)
        return _normalize_weekly_ai_report(ai_report, rule_report)
    except Exception:
        rule_report["summary"] += " AI 分析失败，当前结果由系统规则生成。"
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


async def _get_llm(db: AsyncSession) -> LLMClient | None:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == AI_CONFIG_KEY))
    ).scalar_one_or_none()
    config = setting.value_json if setting else {}
    api_key = (config or {}).get("api_key_encrypted")
    if not api_key:
        return None
    return LLMClient(
        base_url=(config or {}).get("api_base_url") or "",
        api_key=api_key,
        model=(config or {}).get("model_name") or "",
        max_tokens=int((config or {}).get("max_tokens") or 2048),
        temperature=float((config or {}).get("temperature") or 0.7),
    )


async def generate_report_payload(db: AsyncSession, report_type: str) -> dict:
    llm = await _get_llm(db)
    try:
        if report_type == "daily":
            return await daily_brief(db, llm)
        if report_type == "weekly":
            return await generate_weekly_report(db, llm)
        raise ValueError(f"Unsupported report type: {report_type}")
    finally:
        if llm:
            await llm.close()


async def get_report_snapshot(db: AsyncSession, report_type: str) -> dict:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == _snapshot_key(report_type)))
    ).scalar_one_or_none()
    if not setting or not setting.value_json:
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
) -> dict:
    current = now or _now()
    payload = {
        "report_type": report_type,
        "report": report,
        "generated_at": current.isoformat(timespec="seconds"),
        "schedule_key": _schedule_key(report_type, current),
        "trigger": trigger,
    }
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == _snapshot_key(report_type)))
    ).scalar_one_or_none()
    if setting:
        setting.value_json = payload
    else:
        db.add(SystemSetting(key=_snapshot_key(report_type), value_json=payload))
    await db.flush()
    return payload


async def refresh_report_snapshot(
    db: AsyncSession,
    report_type: str,
    trigger: str = "manual",
    now: datetime | None = None,
) -> dict:
    report = await generate_report_payload(db, report_type)
    return await save_report_snapshot(db, report_type, report, trigger, now)


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
