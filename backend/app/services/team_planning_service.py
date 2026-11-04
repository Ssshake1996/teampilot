"""Explicit time allocations and durable team planning records."""
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.models.assignment import Assignment, AssignmentKind
from app.models.task_event import TaskEvent, TaskEventType
from app.config import settings
from app.models.user import User
from app.models.team_planning import (
    WeekCapacity, WeekAllocation, ProjectMilestone, TaskDependency, PlanBaseline,
    WeekCommitment, Retrospective,
)


from app.schemas.task import TaskCreate
from app.schemas.team_planning import (
    CapacityInput, AllocationInput, MilestoneInput, MilestoneUpdate, DependencyInput,
    CommitmentInput, CommitmentUpdate, RetrospectiveInput,
)


def local_today() -> date:
    try:
        return datetime.now(ZoneInfo(settings.REPORT_TIMEZONE)).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).date()


def require_monday(value: date) -> date:
    if value.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    return value


async def active_user(db: AsyncSession, user_id: uuid.UUID):
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise ValueError("User does not exist or is inactive")
    return user


async def task(db: AsyncSession, task_id: uuid.UUID) -> Task:
    item = await db.get(Task, task_id)
    if not item or item.is_deleted:
        raise ValueError("Task not found")
    return item


async def capacity(db: AsyncSession, week_start: date, project_ids: list[uuid.UUID] | None = None) -> dict:
    require_monday(week_start)
    users = (await db.execute(select(User).where(User.is_active == True).order_by(User.full_name))).scalars().all()
    capacities = {row.user_id: row for row in (await db.execute(select(WeekCapacity).where(WeekCapacity.week_start == week_start))).scalars()}
    query = select(WeekAllocation, Task).join(Task, Task.id == WeekAllocation.task_id).where(
        WeekAllocation.week_start == week_start, Task.is_deleted == False,
    )
    if project_ids is not None:
        query = query.where(Task.project_id.in_(project_ids))
    rows = (await db.execute(query)).all()
    parent_ids = set((await db.execute(select(Task.parent_task_id).where(Task.parent_task_id.is_not(None), Task.is_deleted == False))).scalars())
    allocations = [{"id": a.id, "task_id": t.id, "task_title": t.title, "project_id": t.project_id,
                    "user_id": a.user_id, "hours": float(a.hours), "week_start": a.week_start,
                    "excluded_from_total": t.id in parent_ids} for a, t in rows]
    used = {}
    for allocation in allocations:
        if allocation["excluded_from_total"]:
            continue
        used[allocation["user_id"]] = used.get(allocation["user_id"], 0) + allocation["hours"]
    people = []
    for user in users:
        setting = capacities.get(user.id)
        available = float(setting.available_hours) if setting else None
        allocated = round(used.get(user.id, 0), 1)
        people.append({"user_id": user.id, "full_name": user.full_name,
                       "available_hours": available, "allocated_hours": allocated,
                       "gap_hours": round(max(0, allocated - available), 1) if available is not None else None,
                       "note": setting.note if setting else ""})
    return {"week_start": week_start, "scope": "visible_projects_only", "users": people, "allocations": allocations,
            "totals": {"available_hours": round(sum(p["available_hours"] or 0 for p in people), 1),
                       "allocated_hours": round(sum(p["allocated_hours"] for p in people), 1),
                       "over_capacity_hours": round(sum(p["gap_hours"] or 0 for p in people), 1),
                       "capacity_not_set_count": sum(p["available_hours"] is None for p in people)}}


async def save_capacity(db: AsyncSession, week_start: date, data: CapacityInput) -> None:
    require_monday(week_start)
    await active_user(db, data.user_id)
    row = (await db.execute(select(WeekCapacity).where(WeekCapacity.user_id == data.user_id, WeekCapacity.week_start == week_start))).scalar_one_or_none()
    if row is None:
        row = WeekCapacity(user_id=data.user_id, week_start=week_start)
        db.add(row)
    row.available_hours, row.note = data.available_hours, data.note.strip()
    await db.flush()


async def save_allocation(db: AsyncSession, data: AllocationInput) -> WeekAllocation:
    require_monday(data.week_start)
    item = await task(db, data.task_id)
    await active_user(db, data.user_id)
    assigned = (await db.execute(select(Assignment.id).where(
        Assignment.task_id == item.id, Assignment.user_id == data.user_id,
        Assignment.kind == AssignmentKind.TASK_ASSIGNEE,
    ))).first()
    if assigned is None:
        raise ValueError("请先在任务责任面板分配该成员，再安排工时")
    children = (await db.execute(select(Task.id).where(Task.parent_task_id == item.id, Task.is_deleted == False).limit(1))).first()
    if children:
        raise ValueError("Allocate leaf tasks only; parent and child work must not be counted twice")
    row = (await db.execute(select(WeekAllocation).where(WeekAllocation.task_id == data.task_id,
        WeekAllocation.user_id == data.user_id, WeekAllocation.week_start == data.week_start))).scalar_one_or_none()
    if row is None:
        row = WeekAllocation(**data.model_dump())
        db.add(row)
    else:
        row.hours = data.hours
    await db.flush()
    return row


async def validate_milestone_tasks(db: AsyncSession, project_id: uuid.UUID, ids: list[uuid.UUID]) -> list[str]:
    unique = list(dict.fromkeys(ids))
    for task_id in unique:
        item = await task(db, task_id)
        if item.project_id != project_id:
            raise ValueError("Milestone tasks must belong to the same project")
    return [str(value) for value in unique]


async def milestone_out(db: AsyncSession, row: ProjectMilestone) -> dict:
    ids = [uuid.UUID(value) for value in row.task_ids]
    tasks = (await db.execute(select(Task).where(Task.id.in_(ids), Task.is_deleted == False))).scalars().all() if ids else []
    completed = sum(item.status == TaskStatus.DONE for item in tasks)
    return {"id": row.id, "project_id": row.project_id, "name": row.name, "owner_id": row.owner_id,
            "due_date": row.due_date, "task_ids": ids, "completed_tasks": completed, "total_tasks": len(ids),
            "is_overdue": row.due_date < local_today() and (not ids or completed < len(ids))}


async def milestones(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(select(ProjectMilestone).where(ProjectMilestone.project_id == project_id).order_by(ProjectMilestone.due_date))).scalars().all()
    return [await milestone_out(db, row) for row in rows]


async def save_milestone(db: AsyncSession, data: MilestoneInput) -> dict:
    await active_user(db, data.owner_id)
    ids = await validate_milestone_tasks(db, data.project_id, data.task_ids)
    row = ProjectMilestone(**data.model_dump(exclude={"task_ids"}), task_ids=ids)
    db.add(row)
    await db.flush()
    return await milestone_out(db, row)


async def update_milestone(db: AsyncSession, row: ProjectMilestone, data: MilestoneUpdate) -> dict:
    values = data.model_dump(exclude_unset=True, exclude_none=True)
    if "owner_id" in values:
        await active_user(db, values["owner_id"])
    if "task_ids" in values:
        values["task_ids"] = await validate_milestone_tasks(db, row.project_id, values["task_ids"])
    for key, value in values.items():
        setattr(row, key, value)
    await db.flush()
    return await milestone_out(db, row)


async def dependency_out(db: AsyncSession, row: TaskDependency) -> dict:
    predecessor, successor = await db.get(Task, row.predecessor_id), await db.get(Task, row.successor_id)
    now = datetime.now(timezone.utc)
    due = predecessor.deadline
    if due and not due.tzinfo:
        due = due.replace(tzinfo=timezone.utc)
    blocked = predecessor.status != TaskStatus.DONE
    return {"id": row.id, "predecessor_id": row.predecessor_id, "successor_id": row.successor_id,
            "predecessor_title": predecessor.title, "successor_title": successor.title,
            "is_blocked": blocked, "is_upstream_late": bool(blocked and due and due < now)}


async def dependencies(db: AsyncSession, project_id: uuid.UUID, visible_ids: list[uuid.UUID] | None = None) -> list[dict]:
    rows = (await db.execute(select(TaskDependency))).scalars().all()
    result = []
    for row in rows:
        a, b = await db.get(Task, row.predecessor_id), await db.get(Task, row.successor_id)
        if not a or not b or a.is_deleted or b.is_deleted or project_id not in (a.project_id, b.project_id):
            continue
        if visible_ids is not None and (a.project_id not in visible_ids or b.project_id not in visible_ids):
            continue
        result.append(await dependency_out(db, row))
    return result


async def add_dependency(db: AsyncSession, data: DependencyInput) -> dict:
    if data.predecessor_id == data.successor_id:
        raise ValueError("A task cannot depend on itself")
    await task(db, data.predecessor_id)
    await task(db, data.successor_id)
    # Serialize intersecting dependency edits on databases supporting row locks.
    await db.execute(select(Task.id).where(Task.id.in_([data.predecessor_id, data.successor_id]))
                     .order_by(Task.id).with_for_update())
    rows = (await db.execute(select(TaskDependency))).scalars().all()
    active_ids = set((await db.execute(select(Task.id).where(Task.is_deleted == False))).scalars())
    graph = {}
    for row in rows:
        if row.predecessor_id not in active_ids or row.successor_id not in active_ids:
            continue
        if (row.predecessor_id, row.successor_id) == (data.predecessor_id, data.successor_id):
            raise ValueError("Dependency already exists")
        graph.setdefault(row.predecessor_id, []).append(row.successor_id)
    stack, seen = [data.successor_id], set()
    while stack:
        current = stack.pop()
        if current == data.predecessor_id:
            raise ValueError("Dependency would create a cycle")
        if current not in seen:
            seen.add(current)
            stack.extend(graph.get(current, []))
    row = TaskDependency(**data.model_dump())
    db.add(row)
    await db.flush()
    return await dependency_out(db, row)


async def create_baseline(db: AsyncSession, project_id: uuid.UUID, label: str, actor_id: uuid.UUID) -> dict:
    from app.models.task_management import TaskGovernance
    from app.services.task_service import get_task_assignee_map
    tasks = (await db.execute(select(Task).where(Task.project_id == project_id, Task.is_deleted == False))).scalars().all()
    assignments = await get_task_assignee_map(db, tasks)
    governed = {row.task_id: row for row in (await db.execute(select(TaskGovernance).where(TaskGovernance.task_id.in_([item.id for item in tasks])))).scalars()}
    snapshot = [{"task_id": str(item.id), "title": item.title,
                 "deadline": item.deadline.isoformat() if item.deadline else None,
                 "estimated_hours": float(item.estimated_hours) if item.estimated_hours is not None else None,
                 "assignee_ids": sorted(str(entry["user_id"]) for entry in assignments.get(item.id, [])),
                 "owner_id": str(governed[item.id].owner_id) if item.id in governed else None,
                 "reviewer_id": str(governed[item.id].reviewer_id) if item.id in governed else None} for item in tasks]
    row = PlanBaseline(project_id=project_id, label=label.strip(), snapshot_json=snapshot, created_by=actor_id)
    db.add(row)
    await db.flush()
    return next(item for item in await baselines(db, project_id) if item["id"] == row.id)


async def baselines(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    from app.models.task_management import TaskGovernance
    from app.services.task_service import get_task_assignee_map
    rows = (await db.execute(select(PlanBaseline).where(PlanBaseline.project_id == project_id).order_by(PlanBaseline.created_at.desc(), PlanBaseline.id.desc()))).scalars().all()
    result = []
    for row in rows:
        tasks = []
        for original in row.snapshot_json:
            current = await db.get(Task, uuid.UUID(original["task_id"]))
            assigned = await get_task_assignee_map(db, [current]) if current else {}
            assignee_ids = sorted(str(entry["user_id"]) for entry in assigned.get(current.id, [])) if current else []
            governance = await db.get(TaskGovernance, current.id) if current else None
            owner_id = str(governance.owner_id) if governance else None
            reviewer_id = str(governance.reviewer_id) if governance else None
            current_deadline = current.deadline.isoformat() if current and current.deadline else None
            # Compare datetimes by value, ignoring storage-specific timezone formatting.
            old_dt = datetime.fromisoformat(original["deadline"]).replace(tzinfo=None) if original["deadline"] else None
            new_dt = current.deadline.replace(tzinfo=None) if current and current.deadline else None
            hours = float(current.estimated_hours) if current and current.estimated_hours is not None else None
            tasks.append({"task_id": original["task_id"], "title": original["title"],
                          "baseline_deadline": original["deadline"], "current_deadline": current_deadline,
                          "baseline_hours": original["estimated_hours"], "current_hours": hours,
                          "baseline_assignee_ids": original.get("assignee_ids", []), "current_assignee_ids": assignee_ids,
                          "baseline_owner_id": original.get("owner_id"), "current_owner_id": owner_id,
                          "baseline_reviewer_id": original.get("reviewer_id"), "current_reviewer_id": reviewer_id,
                          "is_deleted": not current or current.is_deleted,
                          "changed": not current or current.is_deleted or old_dt != new_dt or original["estimated_hours"] != hours
                              or original.get("assignee_ids", []) != assignee_ids or original.get("owner_id") != owner_id or original.get("reviewer_id") != reviewer_id})
        result.append({"id": row.id, "project_id": row.project_id, "label": row.label, "created_at": row.created_at, "tasks": tasks})
    return result


async def commitment_out(db: AsyncSession, row: WeekCommitment) -> dict:
    item = await db.get(Task, row.task_id)
    end = row.week_start + timedelta(days=6)
    try:
        tz = ZoneInfo(settings.REPORT_TIMEZONE)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    last_event = (await db.execute(select(TaskEvent).where(TaskEvent.task_id == row.task_id,
        TaskEvent.event_type.in_([TaskEventType.SIGNOFF, TaskEventType.REOPEN]), TaskEvent.created_at < end_at
    ).order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc()).limit(1))).scalar_one_or_none()
    signed_off_at = last_event.created_at if last_event and last_event.event_type == TaskEventType.SIGNOFF else None
    if last_event is None and item and item.signed_off_at:
        legacy_date = item.signed_off_at.replace(tzinfo=item.signed_off_at.tzinfo or timezone.utc).astimezone(tz).date()
        signed_off_at = item.signed_off_at if legacy_date <= end else None
    signed_date = signed_off_at.replace(tzinfo=signed_off_at.tzinfo or timezone.utc).astimezone(tz).date() if signed_off_at else None
    delivered = bool(signed_date and row.week_start <= signed_date <= end)
    state = "delivered" if delivered else ("missed" if local_today() > end else "committed")
    return {"id": row.id, "project_id": row.project_id, "task_id": row.task_id,
            "task_title": item.title if item else "Deleted task", "week_start": row.week_start,
            "owner_id": row.owner_id, "expected_outcome": row.expected_outcome, "outcome_note": row.outcome_note,
            "status": state, "signed_off_at": signed_off_at,
            "is_locked": local_today() > end,
            "delivered_late": bool(item and item.signed_off_at and item.signed_off_at.date() > end)}


async def commitments(db: AsyncSession, project_id: uuid.UUID | None, week_start: date | None = None, project_ids: list[uuid.UUID] | None = None) -> list[dict]:
    query = select(WeekCommitment)
    if project_id:
        query = query.where(WeekCommitment.project_id == project_id)
    if week_start:
        query = query.where(WeekCommitment.week_start == require_monday(week_start))
    if project_ids is not None:
        query = query.where(WeekCommitment.project_id.in_(project_ids))
    rows = (await db.execute(query.order_by(WeekCommitment.week_start.desc(), WeekCommitment.created_at))).scalars().all()
    return [await commitment_out(db, row) for row in rows]


async def add_commitment(db: AsyncSession, data: CommitmentInput) -> dict:
    from app.models.task_management import TaskGovernance
    item = await task(db, data.task_id)
    if local_today() > data.week_start + timedelta(days=6):
        raise ValueError("已结束的周不能补建承诺，请在复盘中记录实际情况")
    if item.status == TaskStatus.DONE:
        raise ValueError("已验收任务不能重新登记为未交付周承诺")
    await active_user(db, data.owner_id)
    governance = await db.get(TaskGovernance, item.id)
    if governance and governance.owner_id != data.owner_id:
        raise ValueError("周承诺负责人必须与任务主责一致，请先完成责任交接")
    assigned = (await db.execute(select(Assignment.id).where(Assignment.task_id == item.id,
        Assignment.user_id == data.owner_id, Assignment.kind == AssignmentKind.TASK_ASSIGNEE))).first()
    if assigned is None:
        raise ValueError("请先在任务责任面板分配该负责人")
    existing = (await db.execute(select(WeekCommitment).where(WeekCommitment.task_id == item.id, WeekCommitment.week_start == data.week_start))).scalar_one_or_none()
    if existing:
        raise ValueError("A commitment already exists for this task and week")
    row = WeekCommitment(project_id=item.project_id, **data.model_dump())
    db.add(row)
    await db.flush()
    return await commitment_out(db, row)


async def update_commitment(db: AsyncSession, row: WeekCommitment, data: CommitmentUpdate) -> dict:
    if (data.expected_outcome is not None and data.expected_outcome != row.expected_outcome
            and local_today() > row.week_start + timedelta(days=6)):
        raise ValueError("历史周承诺已冻结，只能补充偏差与下一步说明")
    for key, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(row, key, value)
    await db.flush()
    return await commitment_out(db, row)


async def retrospective_out(db: AsyncSession, row: Retrospective) -> dict:
    from app.models.task_management import TaskGovernance
    actions = []
    for task_id in row.action_task_ids:
        item = await db.get(Task, uuid.UUID(task_id))
        if item:
            from app.services.task_service import get_task_assignee_map
            assignees = (await get_task_assignee_map(db, [item])).get(item.id, [])
            governance = await db.get(TaskGovernance, item.id)
            actions.append({"task_id": item.id, "title": item.title,
                            "owner_id": governance.owner_id if governance else (assignees[0]["user_id"] if assignees else None),
                            "deadline": item.deadline, "status": item.status.value})
    return {"id": row.id, "project_id": row.project_id, "week_start": row.week_start,
            "summary": row.summary, "decisions": row.decisions, "action_tasks": actions,
            "created_at": row.created_at}


async def retrospectives(db: AsyncSession, project_id: uuid.UUID, week_start: date | None = None) -> list[dict]:
    query = select(Retrospective).where(Retrospective.project_id == project_id)
    if week_start:
        query = query.where(Retrospective.week_start == require_monday(week_start))
    rows = (await db.execute(query.order_by(Retrospective.created_at.desc()))).scalars().all()
    return [await retrospective_out(db, row) for row in rows]


async def add_retrospective(db: AsyncSession, data: RetrospectiveInput, actor_id: uuid.UUID) -> dict:
    from app.services.task_service import create_task
    from app.models.task_management import TaskGovernance
    for action in data.actions:
        await active_user(db, action.owner_id)
    row = Retrospective(project_id=data.project_id, week_start=data.week_start,
                        summary=data.summary.strip(), decisions=data.decisions.strip(), created_by=actor_id)
    db.add(row)
    await db.flush()
    ids = []
    for action in data.actions:
        created = await create_task(db, data.project_id, TaskCreate(
            title=action.title.strip(), description=f"复盘改进行动，来源：{row.id}",
            assignee_ids=[action.owner_id], deadline=action.deadline,
        ), actor_id)
        db.add(TaskGovernance(task_id=created.id, owner_id=action.owner_id, reviewer_id=actor_id,
                             acceptance_criteria=action.acceptance_criteria or action.title.strip(),
                             review_status="not_submitted"))
        assignment = (await db.execute(select(Assignment).where(Assignment.task_id == created.id,
            Assignment.user_id == action.owner_id, Assignment.kind == AssignmentKind.TASK_ASSIGNEE))).scalar_one()
        assignment.role = "owner"
        ids.append(str(created.id))
    row.action_task_ids = ids
    await db.flush()
    return await retrospective_out(db, row)


async def weekly_outcomes(db: AsyncSession, period_start: date, period_end: date, project_ids: list[uuid.UUID] | None = None) -> dict:
    monday = period_end - timedelta(days=period_end.weekday())
    items = await commitments(db, None, monday, project_ids)
    owners = {user.id: user.full_name for user in (await db.execute(select(User))).scalars()}
    result = {"commitments": [], "delivered": [], "deviations": [], "next_steps": []}
    for item in items:
        owner = owners.get(item["owner_id"], "未分配")
        line = f"{item['task_title']}（{owner}）：{item['expected_outcome']}"
        result["commitments"].append(line)
        if item["status"] == "delivered":
            result["delivered"].append(line)
        elif item["status"] == "missed":
            result["deviations"].append(line + f"；偏差说明：{item['outcome_note'] or '待补充'}")
        elif item["outcome_note"]:
            result["next_steps"].append(f"{item['task_title']}（{owner}）：{item['outcome_note']}")
    query = select(Retrospective).where(Retrospective.week_start <= monday)
    if project_ids is not None:
        query = query.where(Retrospective.project_id.in_(project_ids))
    for retrospective in (await db.execute(query.order_by(Retrospective.created_at.desc()))).scalars():
        for action in (await retrospective_out(db, retrospective))["action_tasks"]:
            if action["status"] == TaskStatus.DONE.value:
                continue
            deadline = action["deadline"].date().isoformat() if action["deadline"] else "未设截止"
            result["next_steps"].append(f"复盘改进行动：{action['title']}（{owners.get(action['owner_id'], '未分配')}，截止 {deadline}）")
    result["next_steps"] = list(dict.fromkeys(result["next_steps"]))[:30]
    return result
