import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.skill import Skill, UserSkill
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompt_loader import get_system_prompt
from app.services.ai.prompts import TASK_ESTIMATE_USER
from app.services.ai.task_assignment import _active_task_count, _project_candidate_users


async def estimate_task(
    db: AsyncSession, project_id: uuid.UUID, title: str, description: str, llm: LLMClient
) -> dict:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")

    members_text_parts = []
    for user in await _project_candidate_users(db, project_id):
        user_skills = (await db.execute(
            select(Skill.name, UserSkill.proficiency)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
        )).all()
        skills_str = ", ".join(f"{name}({prof})" for name, prof in user_skills) or "none"
        members_text_parts.append(
            f"- ID: {user.id} | {user.full_name} | skills: {skills_str} | "
            f"active_tasks: {await _active_task_count(db, user.id)} | "
            f"bio: {user.bio or 'not provided'}"
        )

    prompt = TASK_ESTIMATE_USER.format(
        task_title=title,
        task_description=description or "none",
        project_name=project.name,
        team_members="\n".join(members_text_parts) or "none",
    )

    sys_prompt = await get_system_prompt(db, "estimate")
    return await llm.chat_json([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ])
