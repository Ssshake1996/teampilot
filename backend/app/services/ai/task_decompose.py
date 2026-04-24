import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill, UserSkill
from app.models.task import Task
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompt_loader import get_system_prompt
from app.services.ai.prompts import TASK_DECOMPOSE_USER
from app.services.ai.task_assignment import _active_task_count, _project_candidate_users


async def decompose_task(db: AsyncSession, task_id: uuid.UUID, llm: LLMClient) -> dict:
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise ValueError("Task not found")

    members_text_parts = []
    for user in await _project_candidate_users(db, task.project_id):
        user_skills = (await db.execute(
            select(Skill.name, UserSkill.proficiency)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
        )).all()
        skills_str = ", ".join(f"{name}({prof})" for name, prof in user_skills) or "none"
        members_text_parts.append(
            f"- ID: {user.id} | name: {user.full_name} | skills: {skills_str} | "
            f"active_tasks: {await _active_task_count(db, user.id)}"
        )

    prompt = TASK_DECOMPOSE_USER.format(
        task_title=task.title,
        task_description=task.description or "none",
        task_priority=task.priority.value,
        estimated_hours=task.estimated_hours or "not estimated",
        deadline=task.deadline or "not set",
        team_members="\n".join(members_text_parts) or "none",
    )

    sys_prompt = await get_system_prompt(db, "decompose")
    return await llm.chat_json([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ])
