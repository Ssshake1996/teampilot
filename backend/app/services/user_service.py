import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.project import Project
from app.models.skill import UserSkill, Skill
from app.schemas.user import UserUpdate


async def list_users(db: AsyncSession, page: int = 1, page_size: int = 20,
                     search: str = "", department: str = "") -> tuple[list[User], int]:
    q = select(User).where(User.is_active == True)
    cq = select(func.count(User.id)).where(User.is_active == True)

    if search:
        like = f"%{search}%"
        q = q.where((User.full_name.contains(search)) | (User.username.contains(search)))
        cq = cq.where((User.full_name.contains(search)) | (User.username.contains(search)))
    if department:
        q = q.where(User.department == department)
        cq = cq.where(User.department == department)

    total = (await db.execute(cq)).scalar()
    result = await db.execute(
        q.order_by(User.department, User.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return result.scalars().all(), total


async def list_departments(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(User.department).where(User.is_active == True, User.department.isnot(None))
        .distinct().order_by(User.department)
    )
    return [r for (r,) in result.all() if r]


async def create_user(db: AsyncSession, data: dict) -> dict:
    from app.utils.security import hash_password
    existing = await db.execute(select(User).where(User.username == data["username"]))
    if existing.scalar_one_or_none():
        raise ValueError("Username already exists")
    user = User(
        username=data["username"],
        hashed_password=hash_password(data.get("password", "123456")),
        full_name=data.get("full_name", data["username"]),
        role=data.get("role", "member"),
        department=data.get("department"),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return {"id": str(user.id), "username": user.username, "full_name": user.full_name}


async def deactivate_user(db: AsyncSession, user_id: uuid.UUID) -> dict:
    user = await get_user(db, user_id)
    if not user:
        raise ValueError("User not found")
    user.is_active = False
    await db.flush()
    return {"message": f"User {user.full_name} deactivated"}


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> User | None:
    user = await get_user(db, user_id)
    if not user:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.flush()
    return user


async def get_user_workload(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    total_q = await db.execute(
        select(func.count(Task.id)).where(Task.assignee_id == user_id, Task.status != TaskStatus.DONE)
    )
    total = total_q.scalar()

    in_progress_q = await db.execute(
        select(func.count(Task.id)).where(Task.assignee_id == user_id, Task.status == TaskStatus.IN_PROGRESS)
    )
    in_progress = in_progress_q.scalar()

    overdue_q = await db.execute(
        select(func.count(Task.id)).where(
            Task.assignee_id == user_id,
            Task.status != TaskStatus.DONE,
            Task.deadline < now,
        )
    )
    overdue = overdue_q.scalar()

    est_q = await db.execute(
        select(func.coalesce(func.sum(Task.estimated_hours), 0)).where(
            Task.assignee_id == user_id, Task.status != TaskStatus.DONE
        )
    )
    est_hours = float(est_q.scalar())

    act_q = await db.execute(
        select(func.coalesce(func.sum(Task.actual_hours), 0)).where(Task.assignee_id == user_id)
    )
    act_hours = float(act_q.scalar())

    user = await get_user(db, user_id)
    return {
        "user_id": user_id,
        "full_name": user.full_name if user else "",
        "total_tasks": total,
        "in_progress_tasks": in_progress,
        "overdue_tasks": overdue,
        "estimated_hours": est_hours,
        "actual_hours": act_hours,
    }


async def get_user_skills(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(UserSkill, Skill)
        .join(Skill, UserSkill.skill_id == Skill.id)
        .where(UserSkill.user_id == user_id)
    )
    rows = result.all()
    return [
        {
            "skill_id": us.skill_id,
            "skill_name": s.name,
            "category": s.category,
            "proficiency": us.proficiency,
        }
        for us, s in rows
    ]


async def get_user_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Get all tasks assigned to a user with project name."""
    result = await db.execute(
        select(Task, Project.name)
        .join(Project, Task.project_id == Project.id)
        .where(Task.assignee_id == user_id, Task.is_deleted == False)
        .order_by(Task.status, Task.deadline)
    )
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "status": t.status.value,
            "priority": t.priority.value,
            "project_id": str(t.project_id),
            "project_name": pname,
            "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
            "deadline": t.deadline.isoformat() if t.deadline else None,
        }
        for t, pname in result.all()
    ]


async def update_user_skills(db: AsyncSession, user_id: uuid.UUID, skills: list[dict]) -> None:
    await db.execute(
        select(UserSkill).where(UserSkill.user_id == user_id)
    )
    # Delete existing
    from sqlalchemy import delete
    await db.execute(delete(UserSkill).where(UserSkill.user_id == user_id))

    for s in skills:
        db.add(UserSkill(user_id=user_id, skill_id=s["skill_id"], proficiency=s["proficiency"]))
    await db.flush()
