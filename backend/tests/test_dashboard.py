"""Tests for dashboard endpoints."""
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.utils.security import hash_password


@pytest.mark.asyncio
async def test_overview(client: AsyncClient, auth_headers):
    """Test dashboard overview stats."""
    res = await client.get("/api/v1/dashboard/overview", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_tasks" in data
    assert "in_progress_tasks" in data
    assert "overdue_tasks" in data
    assert "completion_rate" in data


@pytest.mark.asyncio
async def test_team_workload(client: AsyncClient, auth_headers):
    """Test team workload endpoint."""
    res = await client.get("/api/v1/dashboard/team-workload", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_team_workload_counts_assignees_and_workload_hours(
    client: AsyncClient,
    auth_headers,
    db_session: AsyncSession,
    test_user,
):
    """Team workload should use task assignees and estimated/fallback workload."""
    owner, _ = test_user
    assignee = User(
        id=uuid.uuid4(),
        username="workload_user",
        hashed_password=hash_password("password123"),
        full_name="Workload User",
        role=UserRole.MEMBER,
    )
    db_session.add(assignee)
    project = Project(
        id=uuid.uuid4(),
        name="Workload Project",
        status=ProjectStatus.ACTIVE,
        owner_id=owner.id,
    )
    db_session.add(project)
    parent = Task(
        id=uuid.uuid4(),
        project_id=project.id,
        title="Parent Work",
        status=TaskStatus.IN_PROGRESS,
        creator_id=owner.id,
        estimated_hours=6,
    )
    child_without_estimate = Task(
        id=uuid.uuid4(),
        project_id=project.id,
        parent_task_id=parent.id,
        title="Child Work",
        status=TaskStatus.NOT_STARTED,
        creator_id=owner.id,
        start_date=datetime.utcnow() + timedelta(days=1),
    )
    done_task = Task(
        id=uuid.uuid4(),
        project_id=project.id,
        title="Done Work",
        status=TaskStatus.DONE,
        creator_id=owner.id,
        estimated_hours=20,
    )
    db_session.add_all([parent, child_without_estimate, done_task])
    for task in [parent, child_without_estimate, done_task]:
        db_session.add(Assignment(
            project_id=project.id,
            task_id=task.id,
            user_id=assignee.id,
            kind=AssignmentKind.TASK_ASSIGNEE,
            role="assignee",
        ))
    await db_session.commit()

    res = await client.get("/api/v1/dashboard/team-workload", headers=auth_headers)
    assert res.status_code == 200
    row = next(item for item in res.json() if item["user_id"] == str(assignee.id))
    assert row["assigned_tasks"] == 2
    assert row["in_progress_tasks"] == 1
    assert row["completed_tasks"] == 1
    assert row["workload_hours"] == 10.0


@pytest.mark.asyncio
async def test_recent_activity(client: AsyncClient, auth_headers):
    """Test recent activity endpoint."""
    res = await client.get("/api/v1/dashboard/recent-activity", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
