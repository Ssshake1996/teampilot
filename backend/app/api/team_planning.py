import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.models.team_planning import WeekAllocation, ProjectMilestone, TaskDependency, WeekCommitment
from app.schemas.team_planning import (
    CapacityInput, AllocationInput, MilestoneInput, MilestoneUpdate, DependencyInput,
    BaselineInput, CommitmentInput, CommitmentUpdate, RetrospectiveInput,
)
from app.services import team_planning_service as service
from app.services.project_access_service import get_visible_project_ids, ensure_project_access, ensure_task_access, validate_project_user


class PlanningRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def wrapped(request):
            try:
                return await handler(request)
            except ValueError as error:
                raise HTTPException(400, str(error)) from None
        return wrapped


router = APIRouter(prefix="/management", tags=["Team Planning"], route_class=PlanningRoute)


@router.get("/capacity")
async def capacity(week_start: date, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.capacity(db, week_start, await get_visible_project_ids(db, user))


@router.put("/capacity")
async def save_capacity(data: CapacityInput, week_start: date, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.assign"))):
    await service.save_capacity(db, week_start, data)
    return await service.capacity(db, week_start, await get_visible_project_ids(db, user))


@router.get("/allocations")
async def allocations(week_start: date, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return (await service.capacity(db, week_start, await get_visible_project_ids(db, user)))["allocations"]


@router.post("/allocations", status_code=201)
async def add_allocation(data: AllocationInput, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.assign"))):
    item = await ensure_task_access(db, user, data.task_id, write=True)
    await validate_project_user(db, item.project_id, data.user_id)
    row = await service.save_allocation(db, data)
    return {"id": row.id, "task_id": row.task_id, "user_id": row.user_id, "week_start": row.week_start, "hours": float(row.hours)}


@router.delete("/allocations/{allocation_id}", status_code=204)
async def delete_allocation(allocation_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.assign"))):
    row = await db.get(WeekAllocation, allocation_id)
    if row is None:
        raise HTTPException(404, "Allocation not found")
    await ensure_task_access(db, user, row.task_id, write=True)
    await db.delete(row)


@router.get("/milestones")
async def milestones(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_project_access(db, user, project_id)
    return await service.milestones(db, project_id)


@router.post("/milestones", status_code=201)
async def add_milestone(data: MilestoneInput, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("project.edit"))):
    await ensure_project_access(db, user, data.project_id, write=True)
    await validate_project_user(db, data.project_id, data.owner_id)
    return await service.save_milestone(db, data)


@router.patch("/milestones/{milestone_id}")
async def edit_milestone(milestone_id: uuid.UUID, data: MilestoneUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("project.edit"))):
    row = await db.get(ProjectMilestone, milestone_id)
    if row is None:
        raise HTTPException(404, "Milestone not found")
    await ensure_project_access(db, user, row.project_id, write=True)
    if data.owner_id:
        await validate_project_user(db, row.project_id, data.owner_id)
    return await service.update_milestone(db, row, data)


@router.delete("/milestones/{milestone_id}", status_code=204)
async def delete_milestone(milestone_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("project.edit"))):
    row = await db.get(ProjectMilestone, milestone_id)
    if row is None:
        raise HTTPException(404, "Milestone not found")
    await ensure_project_access(db, user, row.project_id, write=True)
    await db.delete(row)


@router.get("/dependencies")
async def dependencies(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_project_access(db, user, project_id)
    return await service.dependencies(db, project_id, await get_visible_project_ids(db, user))


@router.post("/dependencies", status_code=201)
async def add_dependency(data: DependencyInput, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.edit"))):
    await ensure_task_access(db, user, data.predecessor_id, write=True)
    await ensure_task_access(db, user, data.successor_id, write=True)
    return await service.add_dependency(db, data)


@router.delete("/dependencies/{dependency_id}", status_code=204)
async def delete_dependency(dependency_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.edit"))):
    row = await db.get(TaskDependency, dependency_id)
    if row is None:
        raise HTTPException(404, "Dependency not found")
    await ensure_task_access(db, user, row.predecessor_id, write=True)
    await ensure_task_access(db, user, row.successor_id, write=True)
    await db.delete(row)


@router.post("/projects/{project_id}/baseline", status_code=201)
async def create_baseline(project_id: uuid.UUID, data: BaselineInput, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("project.edit"))):
    await ensure_project_access(db, user, project_id, write=True)
    return await service.create_baseline(db, project_id, data.label, user.id)


@router.get("/baselines")
async def baselines(project_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_project_access(db, user, project_id)
    return await service.baselines(db, project_id)


@router.get("/commitments")
async def commitments(project_id: uuid.UUID, week_start: date | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_project_access(db, user, project_id)
    return await service.commitments(db, project_id, week_start)


@router.post("/commitments", status_code=201)
async def add_commitment(data: CommitmentInput, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.assign"))):
    item = await ensure_task_access(db, user, data.task_id, write=True)
    await validate_project_user(db, item.project_id, data.owner_id)
    return await service.add_commitment(db, data)


@router.patch("/commitments/{commitment_id}")
async def edit_commitment(commitment_id: uuid.UUID, data: CommitmentUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.assign"))):
    row = await db.get(WeekCommitment, commitment_id)
    if row is None:
        raise HTTPException(404, "Commitment not found")
    await ensure_task_access(db, user, row.task_id, write=True)
    return await service.update_commitment(db, row, data)


@router.get("/retrospectives")
async def retrospectives(project_id: uuid.UUID, week_start: date | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_project_access(db, user, project_id)
    return await service.retrospectives(db, project_id, week_start)


@router.post("/retrospectives", status_code=201)
async def add_retrospective(data: RetrospectiveInput, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("task.create"))):
    await ensure_project_access(db, user, data.project_id, write=True)
    for action in data.actions:
        await validate_project_user(db, data.project_id, action.owner_id)
    return await service.add_retrospective(db, data, user.id)
