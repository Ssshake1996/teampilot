import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.capability_service import get_capability_profile

router = APIRouter(prefix="/capabilities", tags=["能力档案"])


@router.get("/{user_id}")
async def get_profile(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await get_capability_profile(db, user_id)
    if not profile:
        return {
            "user_id": str(user_id),
            "summary": None,
            "ai_analysis": None,
            "performance_score": None,
            "on_time_rate": None,
            "last_analyzed_at": None,
        }
    return profile
