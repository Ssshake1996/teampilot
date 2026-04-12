import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.skill import UserSkill, Skill
from app.models.user import User
from app.models.capability_profile import CapabilityProfile
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts import CAPABILITY_ANALYSIS_SYSTEM, CAPABILITY_ANALYSIS_USER


async def analyze_capability(db: AsyncSession, user_id: uuid.UUID, llm: LLMClient) -> dict:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    # Get skills
    user_skills = (await db.execute(
        select(UserSkill, Skill.name, Skill.category)
        .join(Skill, UserSkill.skill_id == Skill.id)
        .where(UserSkill.user_id == user_id)
    )).all()
    skills_text = "\n".join(
        f"- {name} ({cat or '未分类'}): {us.proficiency}/5" for us, name, cat in user_skills
    ) or "暂无技能记录"

    # Task stats
    done = (await db.execute(
        select(func.count(Task.id)).where(Task.assignee_id == user_id, Task.status == TaskStatus.DONE)
    )).scalar()

    on_time = (await db.execute(
        select(func.count(Task.id)).where(
            Task.assignee_id == user_id,
            Task.status == TaskStatus.DONE,
            Task.completed_at <= Task.deadline,
        )
    )).scalar()
    on_time_rate = round(on_time / done * 100, 1) if done > 0 else 0

    # Hours deviation
    est_sum = (await db.execute(
        select(func.sum(Task.estimated_hours)).where(
            Task.assignee_id == user_id, Task.status == TaskStatus.DONE, Task.estimated_hours.isnot(None)
        )
    )).scalar() or 0
    act_sum = (await db.execute(
        select(func.sum(Task.actual_hours)).where(
            Task.assignee_id == user_id, Task.status == TaskStatus.DONE, Task.actual_hours.isnot(None)
        )
    )).scalar() or 0
    deviation = round((float(act_sum) - float(est_sum)) / float(est_sum) * 100, 1) if est_sum > 0 else 0

    # Recent tasks
    recent = (await db.execute(
        select(Task.title, Task.status, Task.priority, Task.completed_at)
        .where(Task.assignee_id == user_id, Task.status == TaskStatus.DONE)
        .order_by(Task.completed_at.desc())
        .limit(10)
    )).all()
    recent_text = "\n".join(
        f"- {title} (优先级: {pri}, 完成时间: {comp})"
        for title, status, pri, comp in recent
    ) or "暂无记录"

    prompt = CAPABILITY_ANALYSIS_USER.format(
        full_name=user.full_name,
        role=user.role.value,
        skills=skills_text,
        completed_tasks=done,
        on_time_rate=on_time_rate,
        hours_deviation=deviation,
        task_categories="综合类型",
        recent_tasks=recent_text,
    )

    result = await llm.chat_json([
        {"role": "system", "content": CAPABILITY_ANALYSIS_SYSTEM},
        {"role": "user", "content": prompt},
    ])

    # Save to capability profile
    profile = (await db.execute(
        select(CapabilityProfile).where(CapabilityProfile.user_id == user_id)
    )).scalar_one_or_none()

    if profile:
        profile.ai_analysis = result
        profile.performance_score = result.get("overall_rating", 0)
        profile.on_time_rate = on_time_rate
        profile.summary = result.get("summary", "")
        profile.last_analyzed_at = datetime.now(timezone.utc)
    else:
        profile = CapabilityProfile(
            user_id=user_id,
            ai_analysis=result,
            performance_score=result.get("overall_rating", 0),
            on_time_rate=on_time_rate,
            summary=result.get("summary", ""),
            last_analyzed_at=datetime.now(timezone.utc),
        )
        db.add(profile)
    await db.flush()

    return result
