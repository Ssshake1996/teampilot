import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts import RISK_ANALYSIS_USER
from app.services.ai.prompt_loader import get_system_prompt
from app.services.task_service import get_task_assignee_map


async def analyze_project_risk(db: AsyncSession, project_id: uuid.UUID, llm: LLMClient) -> dict:
    now = datetime.now(timezone.utc)

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")

    total = (await db.execute(select(func.count(Task.id)).where(Task.project_id == project_id))).scalar()
    done = (
        await db.execute(
            select(func.count(Task.id)).where(Task.project_id == project_id, Task.status == TaskStatus.DONE)
        )
    ).scalar()
    in_progress = (
        await db.execute(
            select(func.count(Task.id)).where(Task.project_id == project_id, Task.status == TaskStatus.IN_PROGRESS)
        )
    ).scalar()
    overdue_count = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.status != TaskStatus.DONE,
                Task.deadline < now,
            )
        )
    ).scalar()

    overdue_task_rows = (
        await db.execute(
            select(Task)
            .where(
                Task.project_id == project_id,
                Task.status != TaskStatus.DONE,
                Task.deadline < now,
            )
            .order_by(Task.deadline)
        )
    ).scalars().all()
    overdue_assignees = await get_task_assignee_map(db, overdue_task_rows)
    overdue_text = "\n".join(
        f"- {task.title} | deadline: {task.deadline} | status: {task.status.value} | assignees: "
        f"{', '.join(item['full_name'] for item in overdue_assignees.get(task.id, []) if item['full_name']) or 'unassigned'}"
        for task in overdue_task_rows
    ) or "none"

    members = (
        await db.execute(
            select(User.id, User.full_name, func.count(Task.id))
            .join(Assignment, Assignment.user_id == User.id)
            .join(Task, Task.id == Assignment.task_id)
            .where(
                Task.project_id == project_id,
                Task.status != TaskStatus.DONE,
                Task.is_deleted == False,
                Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
                User.is_active == True,
            )
            .group_by(User.id, User.full_name)
            .having(func.count(Task.id) > 0)
        )
    ).all()
    workload_text = "\n".join(
        f"- {name}: {count} unfinished tasks" for _, name, count in members
    ) or "none"

    lagging_rows = (
        await db.execute(
            select(Task)
            .where(Task.project_id == project_id, Task.status == TaskStatus.IN_PROGRESS)
        )
    ).scalars().all()
    lagging_assignees = await get_task_assignee_map(db, lagging_rows)
    lagging_text = "\n".join(
        f"- {task.title} | deadline: {task.deadline} | assignees: "
        f"{', '.join(item['full_name'] for item in lagging_assignees.get(task.id, []) if item['full_name']) or 'unassigned'}"
        for task in lagging_rows
    ) or "none"

    parents_with_children = (
        await db.execute(
            select(Task.title, Task.status, Task.deadline).where(
                Task.project_id == project_id,
                Task.status != TaskStatus.DONE,
                Task.id.in_(select(Task.parent_task_id).where(Task.parent_task_id.isnot(None)).distinct()),
            )
        )
    ).all()
    blocked_text = "\n".join(
        f"- {title} | status: {status.value} | deadline: {deadline}"
        for title, status, deadline in parents_with_children
    ) or "none"

    prompt = RISK_ANALYSIS_USER.format(
        project_name=project.name,
        project_status=project.status.value,
        project_end_date=project.end_date or "not set",
        current_date=now.strftime("%Y-%m-%d"),
        total_tasks=total,
        done_tasks=done,
        in_progress_tasks=in_progress,
        overdue_tasks=overdue_count,
        overdue_detail=overdue_text,
        workload_detail=workload_text,
        lagging_detail=lagging_text,
        blocked_detail=blocked_text,
    )

    sys_prompt = await get_system_prompt(db, "risk")
    return await llm.chat_json([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ])
