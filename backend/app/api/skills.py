import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.skill import Skill
from app.models.user import User
from app.schemas.skill import SkillCreate, SkillOut

router = APIRouter(prefix="/skills", tags=["技能"])


@router.get("", response_model=list[SkillOut])
async def list_skills(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Skill)
    if category:
        q = q.where(Skill.category == category)
    result = await db.execute(q.order_by(Skill.name))
    return result.scalars().all()


@router.post("", response_model=SkillOut, status_code=201)
async def create_skill(
    data: SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    skill = Skill(**data.model_dump())
    db.add(skill)
    await db.flush()
    return skill


@router.patch("/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: uuid.UUID,
    data: SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    await db.flush()
    return skill


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.flush()
    return {"message": "Skill deleted"}
