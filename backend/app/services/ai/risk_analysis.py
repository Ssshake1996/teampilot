import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts import RISK_ANALYSIS_SYSTEM, RISK_ANALYSIS_USER


async def analyze_project_risk(db: AsyncSession, project_id: uuid.UUID, llm: LLMClient) -> dict:
    now = datetime.now(timezone.utc)

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")

    # Task stats
    total = (await db.execute(select(func.count(Task.id)).where(Task.project_id == project_id))).scalar()
    done = (await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id, Task.status == TaskStatus.DONE)
    )).scalar()
    in_progress = (await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id, Task.status == TaskStatus.IN_PROGRESS)
    )).scalar()
    overdue_count = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.status != TaskStatus.DONE, Task.deadline < now
        )
    )).scalar()

    # Overdue tasks detail
    overdue_tasks = (await db.execute(
        select(Task.title, Task.deadline, Task.status, User.full_name)
        .outerjoin(User, Task.assignee_id == User.id)
        .where(Task.project_id == project_id, Task.status != TaskStatus.DONE, Task.deadline < now)
        .order_by(Task.deadline)
    )).all()
    overdue_text = "\n".join(
        f"- {title} | 截止: {dl} | 状态: {st.value} | 负责人: {name or '未分配'}"
        for title, dl, st, name in overdue_tasks
    ) or "无"

    # Workload per person
    members = (await db.execute(
        select(User.id, User.full_name, func.count(Task.id))
        .outerjoin(Task, (Task.assignee_id == User.id) & (Task.project_id == project_id) & (Task.status != TaskStatus.DONE))
        .where(User.is_active == True)
        .group_by(User.id, User.full_name)
        .having(func.count(Task.id) > 0)
    )).all()
    workload_text = "\n".join(
        f"- {name}: {count} 个未完成任务" for uid, name, count in members
    ) or "无负载数据"

    # Lagging tasks (in_progress but no recent progress or low %)
    lagging = (await db.execute(
        select(Task.title, Task.status, Task.deadline, User.full_name)
        .outerjoin(User, Task.assignee_id == User.id)
        .where(
            Task.project_id == project_id,
            Task.status == TaskStatus.IN_PROGRESS,
        )
    )).all()
    lagging_text = "\n".join(
        f"- {title} | 截止: {dl} | 负责人: {name or '未分配'}"
        for title, st, dl, name in lagging
    ) or "无"

    # Parent tasks with incomplete subtasks
    parents_with_children = (await db.execute(
        select(Task.title, Task.status, Task.deadline)
        .where(
            Task.project_id == project_id,
            Task.status != TaskStatus.DONE,
            Task.id.in_(select(Task.parent_task_id).where(Task.parent_task_id.isnot(None)).distinct())
        )
    )).all()
    blocked_text = "\n".join(
        f"- {title} | 状态: {st.value} | 截止: {dl}"
        for title, st, dl in parents_with_children
    ) or "无"

    prompt = RISK_ANALYSIS_USER.format(
        project_name=project.name,
        project_status=project.status.value,
        project_end_date=project.end_date or "未设置",
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

    result = await llm.chat_json([
        {"role": "system", "content": RISK_ANALYSIS_SYSTEM},
        {"role": "user", "content": prompt},
    ])
    return result
