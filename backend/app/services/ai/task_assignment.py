import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.skill import Skill, UserSkill
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.ai.llm_client import LLMClient
from app.services.ai.prompt_loader import get_system_prompt
from app.services.ai.prompts import TASK_ASSIGNMENT_USER


def _format_required_skills(payload) -> str:
    if not isinstance(payload, list):
        return "not specified"

    parts: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            name = item.get("name") or item.get("skill_name") or item.get("skill_id")
            level = item.get("min_proficiency") or item.get("proficiency")
            if name:
                parts.append(f"{name}({level})" if level else str(name))
        elif item:
            parts.append(str(item))
    return ", ".join(parts) or "not specified"


async def _project_candidate_users(db: AsyncSession, project_id: uuid.UUID) -> list[User]:
    members = (
        await db.execute(
            select(User)
            .join(Assignment, Assignment.user_id == User.id)
            .where(Assignment.project_id == project_id, User.is_active == True)
            .distinct()
        )
    ).scalars().all()
    if members:
        return members
    return (await db.execute(select(User).where(User.is_active == True))).scalars().all()


async def _active_task_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return (await db.execute(
        select(func.count(Task.id))
        .join(Assignment, Assignment.task_id == Task.id)
        .where(
            Assignment.user_id == user_id,
            Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
            Task.status != TaskStatus.DONE,
            Task.is_deleted == False,
        )
    )).scalar() or 0


async def _completion_rate(db: AsyncSession, user_id: uuid.UUID) -> float:
    total = (await db.execute(
        select(func.count(Task.id))
        .join(Assignment, Assignment.task_id == Task.id)
        .where(
            Assignment.user_id == user_id,
            Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
            Task.is_deleted == False,
        )
    )).scalar() or 0
    if total == 0:
        return 0

    done = (await db.execute(
        select(func.count(Task.id))
        .join(Assignment, Assignment.task_id == Task.id)
        .where(
            Assignment.user_id == user_id,
            Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
            Task.status == TaskStatus.DONE,
            Task.is_deleted == False,
        )
    )).scalar() or 0
    return round(done / total * 100, 1)


async def recommend_assignee(db: AsyncSession, task_id: uuid.UUID, llm: LLMClient) -> dict:
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise ValueError("Task not found")

    candidates_text = []
    for user in await _project_candidate_users(db, task.project_id):
        user_skills = (await db.execute(
            select(UserSkill, Skill.name)
            .join(Skill, UserSkill.skill_id == Skill.id)
            .where(UserSkill.user_id == user.id)
        )).all()
        skills_str = ", ".join(f"{name}({us.proficiency})" for us, name in user_skills) or "none"
        candidates_text.append(
            f"- ID: {user.id} | name: {user.full_name} | skills: {skills_str} | "
            f"active_tasks: {await _active_task_count(db, user.id)} | "
            f"completion_rate: {await _completion_rate(db, user.id)}% | "
            f"bio: {user.bio or 'not provided'}"
        )

    prompt = TASK_ASSIGNMENT_USER.format(
        task_title=task.title,
        task_description=task.description or "none",
        task_priority=task.priority.value,
        estimated_hours=task.estimated_hours or "not estimated",
        required_skills=_format_required_skills(task.required_skills_json),
        candidates="\n".join(candidates_text),
    )

    sys_prompt = await get_system_prompt(db, "task_assign")
    return await llm.chat_json([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ])
