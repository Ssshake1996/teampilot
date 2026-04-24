import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.skill import Skill, UserSkill
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompt_loader import get_system_prompt
from app.services.ai.prompts import CAPABILITY_ANALYSIS_USER


def _rating(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _assigned_task_ids(user_id: uuid.UUID):
    return select(Assignment.task_id).where(
        Assignment.user_id == user_id,
        Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
    )


async def analyze_capability(db: AsyncSession, user_id: uuid.UUID, llm: LLMClient) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    user_skills = (await db.execute(
        select(UserSkill, Skill.name, Skill.category)
        .join(Skill, UserSkill.skill_id == Skill.id)
        .where(UserSkill.user_id == user_id)
    )).all()
    skills_text = "\n".join(
        f"- {name} ({cat or 'uncategorized'}): {us.proficiency}/5"
        for us, name, cat in user_skills
    ) or "none"

    task_ids = _assigned_task_ids(user_id)
    done = (await db.execute(
        select(func.count(Task.id)).where(
            Task.id.in_(task_ids),
            Task.status == TaskStatus.DONE,
            Task.is_deleted == False,
        )
    )).scalar() or 0

    on_time = (await db.execute(
        select(func.count(Task.id)).where(
            Task.id.in_(_assigned_task_ids(user_id)),
            Task.status == TaskStatus.DONE,
            Task.is_deleted == False,
            Task.deadline.isnot(None),
            Task.completed_at <= Task.deadline,
        )
    )).scalar() or 0
    on_time_rate = round(on_time / done * 100, 1) if done > 0 else 0

    est_sum = (await db.execute(
        select(func.sum(Task.estimated_hours)).where(
            Task.id.in_(_assigned_task_ids(user_id)),
            Task.status == TaskStatus.DONE,
            Task.is_deleted == False,
            Task.estimated_hours.isnot(None),
        )
    )).scalar() or 0
    act_sum = (await db.execute(
        select(func.sum(Task.actual_hours)).where(
            Task.id.in_(_assigned_task_ids(user_id)),
            Task.status == TaskStatus.DONE,
            Task.is_deleted == False,
            Task.actual_hours.isnot(None),
        )
    )).scalar() or 0
    deviation = round((float(act_sum) - float(est_sum)) / float(est_sum) * 100, 1) if est_sum > 0 else 0

    recent = (await db.execute(
        select(Task.title, Task.status, Task.priority, Task.completed_at)
        .where(
            Task.id.in_(_assigned_task_ids(user_id)),
            Task.status == TaskStatus.DONE,
            Task.is_deleted == False,
        )
        .order_by(Task.completed_at.desc())
        .limit(10)
    )).all()
    recent_text = "\n".join(
        f"- {title} (priority: {priority.value}, completed_at: {completed_at})"
        for title, _status, priority, completed_at in recent
    ) or "none"

    prompt = CAPABILITY_ANALYSIS_USER.format(
        full_name=user.full_name,
        role=f"{user.role}; bio: {user.bio or 'not provided'}",
        skills=skills_text,
        completed_tasks=done,
        on_time_rate=on_time_rate,
        hours_deviation=deviation,
        task_categories="mixed",
        recent_tasks=recent_text,
    )

    sys_prompt = await get_system_prompt(db, "capability")
    result = await llm.chat_json([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ])

    user.capability_ai_analysis = result
    user.performance_score = _rating(result.get("overall_rating"))
    user.on_time_rate = Decimal(str(on_time_rate))
    user.capability_summary = result.get("summary", "")
    user.last_analyzed_at = datetime.now(timezone.utc)
    await db.flush()

    return result
