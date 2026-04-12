from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.permission import RolePermission, PERMISSION_CATALOG, DEFAULT_PERMISSIONS

router = APIRouter(prefix="/permissions", tags=["权限管理"])

BUILTIN_ROLES = {"admin", "manager", "member"}


@router.get("/catalog")
async def get_catalog(current_user: User = Depends(require_admin)):
    """Get all available permissions grouped by category."""
    return PERMISSION_CATALOG


@router.get("/roles")
async def get_role_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get permissions for all roles (built-in + custom)."""
    result = await db.execute(select(RolePermission).order_by(RolePermission.role))
    db_roles = {rp.role: rp.permissions for rp in result.scalars().all()}

    roles = {}
    # Built-in roles first (with defaults if not customized)
    for role in ["admin", "manager", "member"]:
        roles[role] = {
            "permissions": db_roles.get(role, DEFAULT_PERMISSIONS.get(role, [])),
            "builtin": True,
        }
    # Custom roles
    for role, perms in db_roles.items():
        if role not in BUILTIN_ROLES:
            roles[role] = {"permissions": perms, "builtin": False}
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
    """Create or update permissions for a role."""
    if data.role == "admin":
        raise HTTPException(status_code=400, detail="Admin permissions cannot be modified")
    if not data.role.strip():
        raise HTTPException(status_code=400, detail="Role name cannot be empty")

    result = await db.execute(select(RolePermission).where(RolePermission.role == data.role))
    rp = result.scalar_one_or_none()
    if rp:
        rp.permissions = data.permissions
    else:
        db.add(RolePermission(role=data.role, permissions=data.permissions))
    await db.flush()
    return {"message": f"Role '{data.role}' saved"}


class RoleCreate(BaseModel):
    name: str
    copy_from: str = ""


@router.post("/roles")
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new custom role."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name cannot be empty")

    existing = await db.execute(select(RolePermission).where(RolePermission.role == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role already exists")

    # Copy permissions from another role if specified
    perms = []
    if data.copy_from:
        src = await db.execute(select(RolePermission).where(RolePermission.role == data.copy_from))
        src_rp = src.scalar_one_or_none()
        if src_rp:
            perms = list(src_rp.permissions)
        elif data.copy_from in DEFAULT_PERMISSIONS:
            perms = list(DEFAULT_PERMISSIONS[data.copy_from])

    db.add(RolePermission(role=name, permissions=perms))
    await db.flush()
    return {"message": f"Role '{name}' created", "permissions": perms}


@router.delete("/roles/{role_name}")
async def delete_role(
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a custom role (built-in roles cannot be deleted)."""
    if role_name in BUILTIN_ROLES:
        raise HTTPException(status_code=400, detail="Cannot delete built-in role")

    result = await db.execute(select(RolePermission).where(RolePermission.role == role_name))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Role not found")

    await db.execute(delete(RolePermission).where(RolePermission.role == role_name))
    await db.flush()
    return {"message": f"Role '{role_name}' deleted"}
