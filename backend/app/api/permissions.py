from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_role_permissions as get_effective_role_permissions, require_permission
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.permissions import BUILTIN_ROLES, DEFAULT_PERMISSIONS, PERMISSION_CATALOG, ROLE_PERMISSIONS_KEY

router = APIRouter(prefix="/permissions", tags=["权限管理"])


async def _get_role_map(db: AsyncSession) -> dict[str, list[str]]:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == ROLE_PERMISSIONS_KEY))
    ).scalar_one_or_none()
    if not setting or not isinstance(setting.value_json, dict):
        return {}
    return {str(role): list(permissions or []) for role, permissions in setting.value_json.items()}


async def _save_role_map(db: AsyncSession, role_map: dict[str, list[str]]) -> None:
    setting = (
        await db.execute(select(SystemSetting).where(SystemSetting.key == ROLE_PERMISSIONS_KEY))
    ).scalar_one_or_none()
    if setting:
        setting.value_json = role_map
    else:
        db.add(SystemSetting(key=ROLE_PERMISSIONS_KEY, value_json=role_map))
    await db.flush()


@router.get("/me")
async def get_my_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {
        "role": current_user.role,
        "permissions": await get_effective_role_permissions(db, current_user.role),
    }


@router.get("/catalog")
async def get_catalog(current_user: User = Depends(require_permission("system.role_manage"))):
    return PERMISSION_CATALOG


@router.get("/roles")
async def get_role_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system.role_manage")),
):
    saved_roles = await _get_role_map(db)
    roles = {}

    for role in ["admin", "manager", "member"]:
        roles[role] = {
            "permissions": saved_roles.get(role, DEFAULT_PERMISSIONS.get(role, [])),
            "builtin": True,
        }

    for role, permissions in saved_roles.items():
        if role not in BUILTIN_ROLES:
            roles[role] = {"permissions": permissions, "builtin": False}
    return roles


class RolePermissionUpdate(BaseModel):
    role: str
    permissions: list[str]


@router.put("/roles")
async def update_role_permissions(
    data: RolePermissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system.role_manage")),
):
    role = data.role.strip()
    if role == "admin":
        raise HTTPException(status_code=400, detail="Admin permissions cannot be modified")
    if not role:
        raise HTTPException(status_code=400, detail="Role name cannot be empty")

    role_map = await _get_role_map(db)
    role_map[role] = data.permissions
    await _save_role_map(db, role_map)
    return {"message": f"Role '{role}' saved"}


class RoleCreate(BaseModel):
    name: str
    copy_from: str = ""


@router.post("/roles")
async def create_role(
    data: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system.role_manage")),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name cannot be empty")
    if name in BUILTIN_ROLES:
        raise HTTPException(status_code=400, detail="Built-in role already exists")

    role_map = await _get_role_map(db)
    if name in role_map:
        raise HTTPException(status_code=400, detail="Role already exists")

    permissions = []
    source = data.copy_from.strip()
    if source:
        if source in role_map:
            permissions = list(role_map[source])
        elif source in DEFAULT_PERMISSIONS:
            permissions = list(DEFAULT_PERMISSIONS[source])

    role_map[name] = permissions
    await _save_role_map(db, role_map)
    return {"message": f"Role '{name}' created", "permissions": permissions}


@router.delete("/roles/{role_name}")
async def delete_role(
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system.role_manage")),
):
    if role_name in BUILTIN_ROLES:
        raise HTTPException(status_code=400, detail="Cannot delete built-in role")

    role_map = await _get_role_map(db)
    if role_name not in role_map:
        raise HTTPException(status_code=404, detail="Role not found")

    del role_map[role_name]
    await _save_role_map(db, role_map)
    return {"message": f"Role '{role_name}' deleted"}
