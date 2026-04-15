import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus, TaskRequiredSkill
from app.models.skill import Skill, UserSkill
from app.models.user import User
from app.models.project import ProjectMember
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts import TASK_ASSIGNMENT_USER
from app.services.ai.prompt_loader import get_system_prompt


async def recommend_assignee(db: AsyncSession, task_id: uuid.UUID, llm: LLMClient) -> dict:
    # Fetch task
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise ValueError("Task not found")

    # Fetch required skills
    req_skills = (await db.execute(
        select(TaskRequiredSkill, Skill.name)
        .join(Skill, TaskRequiredSkill.skill_id == Skill.id)
        .where(TaskRequiredSkill.task_id == task_id)
    )).all()
    skills_text = ", ".join(f"{name}(最低{rs.min_proficiency}级)" for rs, name in req_skills) or "未指定"

    # Fetch project members as candidates
    members = (await db.execute(
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == task.project_id, User.is_active == True)
    )).all()

    candidates_text = []
    for pm, user in members:
        # Current workload
        task_count = (await db.execute(
            select(func.count(Task.id)).where(Task.assignee_id == user.id, Task.status != TaskStatus.DONE)
        )).scalar()

        # User skills
        user_skills = (await db.execute(
            select(UserSkill, Skill.name)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
        )).all()
        skills_str = ", ".join(f"{name}({us.proficiency}级)" for us, name in user_skills) or "无记录"

        # Completion rate
        done_count = (await db.execute(
            select(func.count(Task.id)).where(Task.assignee_id == user.id, Task.status == TaskStatus.DONE)
        )).scalar()
        total_assigned = (await db.execute(select(func.count(Task.id)).where(Task.assignee_id == user.id))).scalar()
        completion_rate = round(done_count / total_assigned * 100, 1) if total_assigned > 0 else 0

        candidates_text.append(
            f"- ID: {user.id} | 姓名: {user.full_name} | 技能: {skills_str} | "
            f"当前任务数: {task_count} | 完成率: {completion_rate}% | "
            f"个人介绍: {user.bio or '未填写'}"
        )

    prompt = TASK_ASSIGNMENT_USER.format(
        task_title=task.title,
        task_description=task.description or "无描述",
        task_priority=task.priority.value,
        estimated_hours=task.estimated_hours or "未估算",
        required_skills=skills_text,
        candidates="\n".join(candidates_text),
    )

    sys_prompt = await get_system_prompt(db, "task_assign")
    result = await llm.chat_json([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ])

    return result
