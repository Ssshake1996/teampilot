"""Dashboard values expose their business scope and actionable identities."""
from decimal import Decimal

import pytest

from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType


@pytest.mark.asyncio
async def test_workload_discloses_fallback_estimates_and_excludes_inactive_work(
    client, db_session, test_user, auth_headers,
):
    user, _ = test_user
    project = Project(name="Active work", owner_id=user.id, status=ProjectStatus.ACTIVE)
    archived = Project(name="Archived", owner_id=user.id, status=ProjectStatus.ARCHIVED)
    db_session.add_all([project, archived])
    await db_session.flush()
    root = Task(project_id=project.id, title="Root fallback", creator_id=user.id)
    db_session.add(root)
    await db_session.flush()
    child = Task(project_id=project.id, parent_task_id=root.id, title="Zero estimate fallback", estimated_hours=Decimal("0"), creator_id=user.id)
    db_session.add(child)
    await db_session.flush()
    tasks = [root, child,
        Task(project_id=project.id, parent_task_id=child.id, title="Grandchild fallback", creator_id=user.id),
        Task(project_id=project.id, title="Explicit estimate", estimated_hours=Decimal("6"), creator_id=user.id),
        Task(project_id=project.id, title="Done", status=TaskStatus.DONE, creator_id=user.id),
        Task(project_id=project.id, title="Deleted", is_deleted=True, creator_id=user.id),
        Task(project_id=archived.id, title="Archived task", creator_id=user.id),
    ]
    db_session.add_all(tasks[2:])
    await db_session.flush()
    db_session.add_all([Assignment(project_id=task.project_id, task_id=task.id, user_id=user.id,
        kind=AssignmentKind.TASK_ASSIGNEE) for task in tasks])
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/team-workload", headers=auth_headers)
    assert response.status_code == 200
    item = next(row for row in response.json() if row["user_id"] == str(user.id))
    assert item["assigned_tasks"] == 4
    assert item["completed_tasks"] == 1
    assert item["workload_hours"] == 20
    assert item["fallback_task_count"] == 3
    assert item["fallback_hours"] == 14


@pytest.mark.asyncio
async def test_recent_progress_has_exact_task_destination_and_hides_removed_scope(
    client, db_session, test_user, auth_headers,
):
    user, _ = test_user
    project = Project(name="Current", owner_id=user.id, status=ProjectStatus.ACTIVE)
    archived = Project(name="Archived", owner_id=user.id, status=ProjectStatus.ARCHIVED)
    db_session.add_all([project, archived])
    await db_session.flush()
    task = Task(project_id=project.id, title="Open task", creator_id=user.id)
    deleted = Task(project_id=project.id, title="Deleted", is_deleted=True, creator_id=user.id)
    archived_task = Task(project_id=archived.id, title="Archived", creator_id=user.id)
    db_session.add_all([task, deleted, archived_task])
    await db_session.flush()
    db_session.add_all([TaskEvent(task_id=row.id, actor_id=user.id, event_type=TaskEventType.PROGRESS,
        progress_pct=25, note="Original submitted note") for row in [task, deleted, archived_task]])
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/recent-activity", headers=auth_headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["task_id"] == str(task.id)
    assert rows[0]["project_id"] == str(project.id)
    assert rows[0]["note"] == "Original submitted note"
