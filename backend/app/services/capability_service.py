import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_capability_profile(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    return {
        "user_id": user.id,
        "summary": user.capability_summary,
        "ai_analysis": user.capability_ai_analysis,
        "performance_score": float(user.performance_score) if user.performance_score else None,
        "on_time_rate": float(user.on_time_rate) if user.on_time_rate else None,
        "last_analyzed_at": user.last_analyzed_at,
    }
