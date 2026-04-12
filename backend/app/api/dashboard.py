from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.dashboard import OverviewStats, TeamWorkload, RecentActivity
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/overview", response_model=OverviewStats)
async def overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await dashboard_service.get_overview(db)


@router.get("/team-workload", response_model=list[TeamWorkload])
async def team_workload(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await dashboard_service.get_team_workload(db)


@router.get("/recent-activity", response_model=list[RecentActivity])
async def recent_activity(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await dashboard_service.get_recent_activity(db, limit)


@router.get("/my-tasks")
async def my_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's tasks grouped by urgency quadrant."""
    return await dashboard_service.get_my_tasks_quadrant(db, current_user.id)


@router.get("/project-progress")
async def project_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all active projects with progress stats."""
    return await dashboard_service.get_project_progress(db)
