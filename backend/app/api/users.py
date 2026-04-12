import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.schemas.user import UserOut, UserUpdate, UserWorkload
from app.schemas.skill import UserSkillUpdate, UserSkillOut
from app.services import user_service

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("", response_model=dict)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str = Query("", description="Search by name/username"),
    department: str = Query("", description="Filter by department"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users, total = await user_service.list_users(db, page, page_size, search, department)
    return {
        "items": [UserOut.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/departments")
async def list_departments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await user_service.list_departments(db)


@router.post("", status_code=201)
async def create_user(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await user_service.create_user(db, data)


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await user_service.deactivate_user(db, user_id)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role == "member":
        raise HTTPException(status_code=403, detail="Cannot update other users")
    user = await user_service.update_user(db, user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}/workload", response_model=UserWorkload)
async def get_workload(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await user_service.get_user_workload(db, user_id)


@router.get("/{user_id}/tasks")
async def get_user_tasks(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await user_service.get_user_tasks(db, user_id)


@router.get("/{user_id}/skills", response_model=list[UserSkillOut])
async def get_user_skills(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await user_service.get_user_skills(db, user_id)


@router.put("/{user_id}/skills")
async def update_user_skills(
    user_id: uuid.UUID,
    skills: list[UserSkillUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await user_service.update_user_skills(
        db, user_id, [s.model_dump() for s in skills]
    )
    return {"message": "Skills updated"}
