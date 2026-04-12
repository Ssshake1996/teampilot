from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.permission import RolePermission, PERMISSION_CATALOG, DEFAULT_PERMISSIONS

router = APIRouter(prefix="/permissions", tags=["权限管理"])


@router.get("/catalog")
async def get_catalog(current_user: User = Depends(require_admin)):
    """Get all available permissions grouped by category."""
    return PERMISSION_CATALOG


@router.get("/roles")
async def get_role_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get permissions for each role."""
    result = await db.execute(select(RolePermission))
    db_roles = {rp.role: rp.permissions for rp in result.scalars().all()}

    roles = {}
    for role in ["admin", "manager", "member"]:
        roles[role] = db_roles.get(role, DEFAULT_PERMISSIONS.get(role, []))
    return roles


class RolePermissionUpdate(BaseModel):
    role: str
    permissions: list[str]


@router.put("/roles")
async def update_role_permissions(
    data: RolePermissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update permissions for a role."""
    if data.role not in ("admin", "manager", "member"):
        return {"error": "Invalid role"}

    result = await db.execute(select(RolePermission).where(RolePermission.role == data.role))
    rp = result.scalar_one_or_none()
    if rp:
        rp.permissions = data.permissions
    else:
        db.add(RolePermission(role=data.role, permissions=data.permissions))
    await db.flush()
    return {"message": f"Role '{data.role}' permissions updated"}
