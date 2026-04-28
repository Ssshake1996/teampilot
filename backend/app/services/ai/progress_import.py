import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.task_service import effective_task_status, get_task_assignee_map, get_task_progress_pct


def _fallback_parse(raw_text: str) -> dict:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) < 3:
        return {"updates": [], "unmatched": []}
    return {
        "updates": [{
            "person_name": lines[0],
            "reported_at": lines[1],
            "raw_text": "\n".join(lines[2:]),
            "task_id": None,
            "task_title": "",
            "progress_pct": None,
            "note": "\n".join(lines[2:]),
            "confidence": 0,
            "reason": "AI 未返回有效 JSON，已保留原始进展供手动确认",
        }],
        "unmatched": [],
    }


def _extract_json_list(data: dict) -> list[dict]:
    updates = data.get("updates", [])
    if isinstance(updates, list):
        return [item for item in updates if isinstance(item, dict)]
    return []


async def parse_progress_updates(
    db: AsyncSession,
    raw_text: str,
    llm: LLMClient,
    project_id: uuid.UUID | None = None,
) -> dict:
    filters = [
        Task.is_deleted == False,
        Task.status != TaskStatus.DONE,
        Project.status != ProjectStatus.ARCHIVED,
    ]
    if project_id:
        filters.append(Task.project_id == project_id)

    rows = (
        await db.execute(
            select(Task, Project.name)
            .join(Project, Task.project_id == Project.id)
            .where(*filters)
            .order_by(Task.created_at.desc())
        )
    ).all()
    assignee_map = await get_task_assignee_map(db, [task for task, _ in rows])

    tasks = []
    for task, project_name in rows:
        assignee_names = [item["full_name"] for item in assignee_map.get(task.id, []) if item["full_name"]]
        tasks.append({
            "id": str(task.id),
            "project_id": str(task.project_id),
            "project_name": project_name,
            "title": task.title,
            "goal": task.goal or "",
            "description": task.description or "",
            "assignee_name": "、".join(assignee_names),
            "status": effective_task_status(task).value,
            "progress_pct": await get_task_progress_pct(db, task),
            "start_date": task.start_date.isoformat() if task.start_date else "",
            "deadline": task.deadline.isoformat() if task.deadline else "",
        })

    if not tasks:
        return {"updates": [], "unmatched": [{"raw_text": raw_text, "reason": "没有可更新的未完成任务"}]}

    messages = [
        {
            "role": "system",
            "content": (
                "你是项目进展录入助手。用户会粘贴跨项目群消息，格式通常是：姓名、时间、任务进展，"
                "一个人的进展可能包含多个任务。请把进展拆分并匹配到给定任务列表。"
                "只返回 JSON，不要返回 Markdown。JSON 结构："
                "{\"updates\":[{\"person_name\":\"\",\"reported_at\":\"\",\"raw_text\":\"\","
                "\"task_id\":\"\",\"project_id\":\"\",\"project_name\":\"\",\"task_title\":\"\",\"progress_pct\":0,\"note\":\"\","
                "\"confidence\":0,\"reason\":\"\"}],\"unmatched\":[{\"person_name\":\"\","
                "\"reported_at\":\"\",\"raw_text\":\"\",\"reason\":\"\"}]}。"
                "progress_pct 必须是 0-100 的整数；如果原文没有百分比，请按语义保守估计："
                "刚开始 10，处理中 40，完成大半 70，已完成/已上线/已交付 100。"
                "只使用任务列表里的 task_id；无法可靠匹配时放入 unmatched。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "project_tasks": tasks,
                "group_message": raw_text,
                "today": datetime.utcnow().date().isoformat(),
            }, ensure_ascii=False),
        },
    ]

    try:
        parsed = await llm.chat_json(messages, temperature=0.1, max_tokens=4096)
    except Exception:
        return _fallback_parse(raw_text)

    task_map = {task["id"]: task for task in tasks}
    updates = []
    for item in _extract_json_list(parsed):
        task_id = item.get("task_id")
        task = task_map.get(str(task_id)) if task_id else None
        if not task:
            continue
        progress_pct = item.get("progress_pct")
        try:
            progress_pct = int(progress_pct)
        except (TypeError, ValueError):
            progress_pct = task["progress_pct"]
        progress_pct = max(0, min(100, progress_pct))
        updates.append({
            "person_name": item.get("person_name") or "",
            "reported_at": item.get("reported_at") or "",
            "raw_text": item.get("raw_text") or item.get("note") or "",
            "task_id": task["id"],
            "project_id": task["project_id"],
            "project_name": task["project_name"],
            "task_title": task["title"],
            "assignee_name": task["assignee_name"],
            "current_progress_pct": task["progress_pct"],
            "progress_pct": progress_pct,
            "note": item.get("note") or item.get("raw_text") or "",
            "confidence": int(item.get("confidence") or 0),
            "reason": item.get("reason") or "",
        })

    unmatched = parsed.get("unmatched", [])
    if not isinstance(unmatched, list):
        unmatched = []
    return {"updates": updates, "unmatched": unmatched}
