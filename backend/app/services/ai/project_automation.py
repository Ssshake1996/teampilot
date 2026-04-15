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
    rows = (await db.execute(
        select(User.id, User.full_name, User.department, User.bio)
        .where(User.is_active == True)
        .order_by(User.full_name)
    )).all()
    return [
        {
            "id": str(user_id),
            "name": name,
            "department": department or "",
            "bio": bio or "",
        }
        for user_id, name, department, bio in rows
    ]


async def _project_snapshot(db: AsyncSession, include_tasks: bool = True) -> list[dict]:
    projects = (await db.execute(
        select(Project)
        .where(Project.status != ProjectStatus.ARCHIVED)
        .order_by(Project.created_at.desc())
    )).scalars().all()

    items = []
    for project in projects:
        total = (await db.execute(
            select(func.count(Task.id)).where(Task.project_id == project.id, Task.is_deleted == False)
        )).scalar() or 0
        done = (await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project.id,
                Task.status == TaskStatus.DONE,
                Task.is_deleted == False,
            )
        )).scalar() or 0
        item = {
            "id": str(project.id),
            "name": project.name,
            "status": project.status.value,
            "start_date": project.start_date,
            "end_date": project.end_date,
            "task_count": total,
            "completed_count": done,
            "completion_rate": round(done / total * 100) if total else 0,
        }
        if include_tasks:
            task_rows = (await db.execute(
                select(Task, User.full_name)
                .outerjoin(User, Task.assignee_id == User.id)
                .where(Task.project_id == project.id, Task.is_deleted == False)
                .order_by(Task.created_at.desc())
                .limit(30)
            )).all()
            item["tasks"] = [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "status": task_service.effective_task_status(task).value,
                    "progress_pct": await task_service.get_task_progress_pct(db, task),
                    "assignee": assignee or "",
                    "deadline": task.deadline,
                    "completed_at": task.completed_at,
                    "signed_off_at": task.signed_off_at,
                }
                for task, assignee in task_rows
            ]
        items.append(item)
    return items


async def preview_project_plan(db: AsyncSession, prompt: str, llm: LLMClient) -> dict:
    users = await _active_users(db)
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深项目经理。根据用户的自然语言目标生成可执行项目计划。"
                "只返回 JSON，不要 Markdown。JSON 结构："
                "{\"project\":{\"name\":\"\",\"description\":\"\",\"start_date\":\"YYYY-MM-DD\","
                "\"end_date\":\"YYYY-MM-DD\"},\"tasks\":[{\"title\":\"\",\"description\":\"\","
                "\"priority\":\"medium\",\"estimated_hours\":8,\"start_date\":\"YYYY-MM-DD\","
                "\"deadline\":\"YYYY-MM-DD\",\"assignee_id\":\"\",\"assignee_name\":\"\","
                "\"reason\":\"\",\"children\":[同结构，children 可省略]}]}。"
                "priority 只能是 low/medium/high/urgent。负责人只能从成员列表中选择；不确定则留空。"
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
    result.setdefault("tasks", [])
    return result


async def commit_project_plan(db: AsyncSession, plan: dict, owner_id: uuid.UUID) -> dict:
    project_data = plan.get("project") or {}
    project = await project_service.create_project(
        db,
        ProjectCreate(
            name=project_data.get("name") or "AI 生成项目",
            description=project_data.get("description") or "",
            start_date=_parse_date(project_data.get("start_date")),
            end_date=_parse_date(project_data.get("end_date")),
        ),
        owner_id,
    )

    created_tasks = []

    async def create_task_item(item: dict, parent_id: uuid.UUID | None = None) -> None:
        assignee_id = None
        raw_assignee = item.get("assignee_id")
        if raw_assignee:
            try:
                assignee_id = uuid.UUID(str(raw_assignee))
            except ValueError:
                assignee_id = None

        task = await task_service.create_task(
            db,
            project.id,
            TaskCreate(
                title=item.get("title") or "未命名任务",
                description=item.get("description") or "",
                priority=_priority(item.get("priority")),
                assignee_id=assignee_id,
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


async def daily_brief(db: AsyncSession, llm: LLMClient) -> dict:
    projects = await _project_snapshot(db, include_tasks=True)
    recent_rows = (await db.execute(
        select(TaskProgress, Task.title, Project.name, User.full_name)
        .join(Task, TaskProgress.task_id == Task.id)
        .join(Project, Task.project_id == Project.id)
        .join(User, TaskProgress.user_id == User.id)
        .where(Project.status != ProjectStatus.ARCHIVED)
        .order_by(TaskProgress.created_at.desc())
        .limit(80)
    )).all()
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
    messages = [
        {
            "role": "system",
            "content": (
                "你是项目 PMO 助手。基于项目、任务和最近进展生成今日管理简报。"
                "只返回 JSON：{\"summary\":\"\",\"completed\":[],\"in_progress\":[],"
                "\"risks\":[],\"actions\":[],\"signoff_candidates\":[]}。"
                "risks 要关注延期、长期无进展、100% 未会签、负载异常、进展描述中的阻塞。"
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
    return await llm.chat_json(messages, temperature=0.2, max_tokens=4096)


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
                "你是任务会签助手。判断任务是否适合会签。"
                "只返回 JSON：{\"recommendation\":\"approve|hold\","
                "\"summary\":\"\",\"checks\":[],\"risks\":[],\"questions\":[]}。"
                "如果进度未到 100%、子任务未完成、历史记录仍有待测试/待确认/阻塞，应建议 hold。"
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
    progress_rows = (await db.execute(
        select(TaskProgress, Task.title, User.full_name)
        .join(Task, TaskProgress.task_id == Task.id)
        .join(User, TaskProgress.user_id == User.id)
        .where(Task.project_id == project_id)
        .order_by(TaskProgress.created_at.desc())
        .limit(120)
    )).all()
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
                "你是项目复盘专家。根据任务树和进展历史总结经验。"
                "只返回 JSON：{\"summary\":\"\",\"wins\":[],\"issues\":[],"
                "\"estimation_lessons\":[],\"process_improvements\":[],\"reusable_template\":[]}。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "project": {
                    "name": project.name,
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
