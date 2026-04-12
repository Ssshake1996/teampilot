import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.project import ProjectMember
from app.models.skill import UserSkill, Skill
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts import TASK_ESTIMATE_SYSTEM, TASK_ESTIMATE_USER


async def estimate_task(
    db: AsyncSession, project_id: uuid.UUID, title: str, description: str, llm: LLMClient
) -> dict:
    from app.models.project import Project

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")

    # Get project members with skills and workload
    members = (await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id, User.is_active == True)
    )).all()

    members_text_parts = []
    for pm, user in members:
        user_skills = (await db.execute(
            select(Skill.name, UserSkill.proficiency)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
        )).all()
        skills_str = ", ".join(f"{name}({prof})" for name, prof in user_skills) or "无"

        task_count = (await db.execute(
            select(func.count(Task.id)).where(Task.assignee_id == user.id, Task.status != TaskStatus.DONE)
        )).scalar()

        members_text_parts.append(
            f"- ID: {user.id} | {user.full_name} | 技能: {skills_str} | 当前任务: {task_count}个"
        )

    prompt = TASK_ESTIMATE_USER.format(
        task_title=title,
        task_description=description or "无详细描述",
        project_name=project.name,
        team_members="\n".join(members_text_parts) or "无成员",
    )

    return await llm.chat_json([
        {"role": "system", "content": TASK_ESTIMATE_SYSTEM},
        {"role": "user", "content": prompt},
    ])
