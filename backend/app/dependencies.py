import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.permission import DEFAULT_PERMISSIONS, RolePermission
from app.models.user import User
from app.utils.security import decode_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def require_manager(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_role_permissions(db: AsyncSession, role: str) -> list[str]:
    """Return effective permissions for a role, including built-in defaults."""
    if role == "admin":
        return list(DEFAULT_PERMISSIONS["admin"])

    result = await db.execute(select(RolePermission).where(RolePermission.role == role))
    role_permission = result.scalar_one_or_none()
    if role_permission:
        return list(role_permission.permissions or [])

    return list(DEFAULT_PERMISSIONS.get(role, []))


async def user_has_permission(db: AsyncSession, user: User, permission: str) -> bool:
    if user.role == "admin":
        return True
    return permission in await get_role_permissions(db, user.role)


def require_permission(permission: str) -> Callable:
    async def dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not await user_has_permission(db, current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return current_user

    return dependency
