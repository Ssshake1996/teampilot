import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_permission, user_has_permission
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


@router.get("/overview")
async def users_overview(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    search: str = Query("", description="Search by name/username"),
    department: str = Query("", description="Filter by department"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await user_service.get_users_overview(db, page, page_size, search, department)
    data["items"] = [
        {
            **item,
            "user": UserOut.model_validate(item["user"]),
        }
        for item in data["items"]
    ]
    data["departments"] = await user_service.list_departments(db)
    return data


@router.post("", status_code=201)
async def create_user(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("personnel.add")),
):
    target_role = data.get("role", "member")
    if target_role != "member" and not await user_has_permission(db, current_user, "system.role_manage"):
        raise HTTPException(status_code=403, detail="Permission required: system.role_manage")
    return await user_service.create_user(db, data)


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("personnel.deactivate")),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
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
    payload = data.model_dump(exclude_unset=True)
    if "role" in payload and not await user_has_permission(db, current_user, "system.role_manage"):
        raise HTTPException(status_code=403, detail="Permission required: system.role_manage")
    profile_fields = set(payload) - {"role"}
    if current_user.id != user_id and profile_fields and not await user_has_permission(db, current_user, "personnel.edit"):
        raise HTTPException(status_code=403, detail="Permission required: personnel.edit")
    user = await user_service.update_user(db, user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}/detail-bundle")
async def get_user_detail_bundle(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await user_service.get_user_detail_bundle(db, user_id)
    if not data:
        raise HTTPException(status_code=404, detail="User not found")
    data["user"] = UserOut.model_validate(data["user"])
    return data


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
    current_user: User = Depends(require_permission("personnel.edit_skills")),
):
    await user_service.update_user_skills(
        db, user_id, [s.model_dump() for s in skills]
    )
    return {"message": "Skills updated"}
