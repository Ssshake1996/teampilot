import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.project import ProjectMember
from app.models.skill import UserSkill, Skill
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts import TASK_DECOMPOSE_SYSTEM, TASK_DECOMPOSE_USER


async def decompose_task(db: AsyncSession, task_id: uuid.UUID, llm: LLMClient) -> dict:
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise ValueError("Task not found")

    # Get project members with skills
    members = (await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == task.project_id, User.is_active == True)
    )).all()

    members_text_parts = []
    for pm, user in members:
        # User skills
        user_skills = (await db.execute(
            select(Skill.name, UserSkill.proficiency)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
        )).all()
        skills_str = ", ".join(f"{name}({prof}级)" for name, prof in user_skills) or "无记录"

        # Current task count
        task_count = (await db.execute(
            select(func.count(Task.id)).where(Task.assignee_id == user.id, Task.status != TaskStatus.DONE)
        )).scalar()

        members_text_parts.append(
            f"- ID: {user.id} | 姓名: {user.full_name} | 技能: {skills_str} | 当前任务数: {task_count}"
        )

    prompt = TASK_DECOMPOSE_USER.format(
        task_title=task.title,
        task_description=task.description or "无详细描述",
        task_priority=task.priority.value,
        estimated_hours=task.estimated_hours or "未估算",
        deadline=task.deadline or "未设置",
        team_members="\n".join(members_text_parts) or "无成员数据",
    )

    result = await llm.chat_json([
        {"role": "system", "content": TASK_DECOMPOSE_SYSTEM},
        {"role": "user", "content": prompt},
    ])
    return result
