"""Read-only DSH queries use the isolated database from conftest.py."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select

from app.models.assignment import Assignment, AssignmentKind
from app.models.dsh_draft import DshDraft
from app.models.project import Project, ProjectStatus
from app.models.system_setting import SystemSetting
from app.models.task import Task, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User, UserRole
from app.services import task_service
from app.utils.security import create_access_token

BASE = "/api/v1/integrations/dsh"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def seed(db, owner):
    other = User(username="query-other", full_name="Other Actor", role=UserRole.MEMBER,
        hashed_password="unused-test-hash")
    projects = [Project(name=name, owner_id=owner.id, status=status) for name, status in (
        ("First", ProjectStatus.ACTIVE), ("Second", ProjectStatus.ACTIVE), ("Archived", ProjectStatus.ARCHIVED))]
    db.add_all([other, *projects])
    await db.flush()
    tasks = [
        Task(project_id=projects[0].id, creator_id=owner.id, title="Primary repair", description="Investigate delivery",
            status=TaskStatus.IN_PROGRESS, created_at=START),
        Task(project_id=projects[0].id, creator_id=owner.id, title="Future repair", status=TaskStatus.IN_PROGRESS,
            start_date=datetime.now(timezone.utc) + timedelta(days=2), created_at=START),
        Task(project_id=projects[1].id, creator_id=owner.id, title="Other project work", status=TaskStatus.IN_PROGRESS, created_at=START),
        Task(project_id=projects[0].id, creator_id=owner.id, title="Deleted repair", is_deleted=True, created_at=START),
        Task(project_id=projects[2].id, creator_id=owner.id, title="Archived repair", created_at=START),
    ]
    db.add_all(tasks)
    await db.flush()
    db.add_all([Assignment(project_id=task.project_id, task_id=task.id, user_id=actor.id,
        kind=AssignmentKind.TASK_ASSIGNEE) for task, actor in (
            (tasks[0], owner), (tasks[0], other), (tasks[1], other), (tasks[2], owner))])
    events = [TaskEvent(id=uuid.UUID(int=100 + index), task_id=task.id, actor_id=actor.id,
        event_type=TaskEventType.PROGRESS, progress_pct=pct, note=f"update-{index}", hours_spent=hours,
        created_at=START + timedelta(hours=index)) for index, (task, actor, pct, hours) in enumerate((
            (tasks[0], owner, 10, 0), (tasks[0], other, 20, 1.5), (tasks[1], owner, 30, None),
            (tasks[2], owner, 40, None), (tasks[3], owner, 50, None), (tasks[4], owner, 60, None)))]
    db.add_all(events)
    db.add(TaskEvent(task_id=tasks[0].id, actor_id=owner.id, event_type=TaskEventType.SIGNOFF,
        created_at=START + timedelta(hours=1)))
    await db.commit()
    return projects, tasks, other, events


@pytest.mark.asyncio
async def test_task_queries_filter_before_paging_and_use_effective_status(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    projects, tasks, _, _ = await seed(db_session, owner)
    response = await client.get(f"{BASE}/tasks", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 3
    assert {row["id"] for row in data["items"]} == {str(task.id) for task in tasks[:3]}
    assert data["scope"]["include_archived"] is False
    assert data["scope"]["include_deleted"] is False

    response = await client.get(f"{BASE}/tasks", headers=auth_headers, params={
        "project_id": str(projects[0].id), "assignee_id": str(owner.id), "status": "in_progress",
        "search": "REPAIR", "page_size": 1})
    data = response.json()
    assert data["total"] == 1 and data["items"][0]["id"] == str(tasks[0].id)
    assert data["items"][0]["project_name"] == "First"
    assert data["items"][0]["progress_pct"] == 20
    assert data["scope"]["assignee_id"] == str(owner.id)
    future = (await client.get(f"{BASE}/tasks", headers=auth_headers, params={"status": "not_started"})).json()
    assert future["total"] == 1 and future["items"][0]["id"] == str(tasks[1].id)
    assert future["items"][0]["status"] == "not_started"


@pytest.mark.asyncio
async def test_task_queries_page_deterministically_beyond_first_fifty(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    project = Project(name="Many tasks", owner_id=owner.id)
    db_session.add(project)
    await db_session.flush()
    tasks = [Task(id=uuid.UUID(int=index), project_id=project.id, creator_id=owner.id,
        title=f"task-{index}", created_at=START) for index in range(1, 56)]
    db_session.add_all(tasks)
    await db_session.commit()
    first = await client.get(f"{BASE}/tasks", headers=auth_headers)
    assert first.status_code == 200, first.text
    first = first.json()
    second = (await client.get(f"{BASE}/tasks?page=2", headers=auth_headers)).json()
    assert first["total"] == second["total"] == 55
    assert first["page_size"] == 50 and first["has_more"] is True and second["has_more"] is False
    ids = [row["id"] for row in first["items"] + second["items"]]
    assert ids == [str(task.id) for task in reversed(tasks)]
    assert (await client.get(f"{BASE}/tasks?page_size=101", headers=auth_headers)).status_code == 422


@pytest.mark.asyncio
async def test_filtered_task_query_preserves_weighted_children_progress(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    project = Project(name="Weighted", owner_id=owner.id)
    db_session.add(project)
    await db_session.flush()
    parent = Task(project_id=project.id, creator_id=owner.id, title="Selected parent")
    db_session.add(parent)
    await db_session.flush()
    children = [Task(project_id=project.id, creator_id=owner.id, title=f"child-{index}",
        parent_task_id=parent.id, weight=weight) for index, weight in enumerate((0.25, 0.75))]
    db_session.add_all(children)
    await db_session.flush()
    db_session.add_all([TaskEvent(task_id=task.id, actor_id=owner.id, event_type=TaskEventType.PROGRESS,
        progress_pct=pct) for task, pct in zip(children, (20, 80))])
    await db_session.commit()
    response = await client.get(f"{BASE}/tasks?search=Selected", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    existing = (await client.get(f"/api/v1/tasks/{parent.id}", headers=auth_headers)).json()
    assert data["total"] == 1
    assert data["items"][0]["progress_pct"] == existing["progress_pct"] == 65


@pytest.mark.asyncio
async def test_progress_queries_filter_actor_task_project_and_utc_boundaries(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    projects, tasks, other, events = await seed(db_session, owner)
    response = await client.get(f"{BASE}/progress", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 4
    assert {row["id"] for row in data["items"]} == {str(log.id) for log in events[:4]}
    assert data["scope"]["include_archived"] is False and data["scope"]["include_deleted"] is False

    response = await client.get(f"{BASE}/progress", headers=auth_headers, params={
        "project_id": str(projects[0].id), "task_id": str(tasks[0].id), "user_id": str(owner.id),
        "since": "2026-01-01T09:00:00+09:00", "until": "2026-01-01T01:00:00Z"})
    data = response.json()
    assert data["total"] == 1
    row = data["items"][0]
    assert row["id"] == str(events[0].id) and row["hours_spent"] == 0
    assert row["project_name"] == "First" and row["task_title"] == "Primary repair"
    assert row["user_name"] == owner.full_name and row["note"] == "update-0"
    assert datetime.fromisoformat(row["created_at"]).utcoffset() == timedelta(0)
    assert data["scope"]["timezone"] == "UTC"
    other_data = (await client.get(f"{BASE}/progress", headers=auth_headers, params={"user_id": str(other.id)})).json()
    assert other_data["total"] == 1 and other_data["items"][0]["id"] == str(events[1].id)
    boundary = (await client.get(f"{BASE}/progress", headers=auth_headers,
        params={"since": "2026-01-01T00:00:00.000001Z", "until": "2026-01-01T01:00:00Z"})).json()
    assert boundary["total"] == 0


@pytest.mark.asyncio
async def test_progress_queries_are_complete_and_deterministically_paged(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    project = Project(name="Many updates", owner_id=owner.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(project_id=project.id, creator_id=owner.id, title="Frequently updated")
    db_session.add(task)
    await db_session.flush()
    logs = [TaskEvent(id=uuid.UUID(int=index), task_id=task.id, actor_id=owner.id,
        event_type=TaskEventType.PROGRESS, progress_pct=index, created_at=START) for index in range(1, 62)]
    db_session.add_all(logs)
    await db_session.commit()
    first = await client.get(f"{BASE}/progress", headers=auth_headers)
    assert first.status_code == 200, first.text
    first = first.json()
    second = (await client.get(f"{BASE}/progress?page=2", headers=auth_headers)).json()
    assert first["total"] == second["total"] == 61
    assert first["has_more"] is True and second["has_more"] is False
    assert [row["id"] for row in first["items"] + second["items"]] == [str(log.id) for log in reversed(logs)]
    empty = (await client.get(f"{BASE}/progress?page=3", headers=auth_headers)).json()
    assert empty["items"] == [] and empty["total"] == 61 and empty["has_more"] is False


@pytest.mark.asyncio
async def test_progress_queries_validate_intervals_and_recheck_permission(client, auth_headers, db_session, test_user):
    for params in ({"since": "invalid"}, {"since": "2026-01-02", "until": "2026-01-01"}, {"page_size": 101}):
        assert (await client.get(f"{BASE}/progress", headers=auth_headers, params=params)).status_code == 422
    owner, _ = test_user
    owner.role = UserRole.MEMBER
    db_session.add(SystemSetting(key="role_permissions", value_json={"member": []}))
    await db_session.commit()
    assert (await client.get(f"{BASE}/progress", headers=auth_headers)).status_code == 403
    assert (await client.get(f"{BASE}/tasks", headers=auth_headers)).status_code == 200
    for suffix in ("tasks", "progress"):
        assert (await client.get(f"{BASE}/{suffix}")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_query_gets_are_readonly_and_expose_no_secret_fields(client, auth_headers, db_session, test_user):
    await seed(db_session, test_user[0])
    tables = (Project, Task, TaskEvent, DshDraft, SystemSetting)
    before = [(await db_session.execute(select(func.count()).select_from(model))).scalar() for model in tables]
    statements = []
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
    try:
        responses = [await client.get(f"{BASE}/{suffix}", headers=auth_headers) for suffix in ("tasks", "progress")]
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)
    for response in responses:
        assert response.status_code == 200, response.text
        def check(value):
            if isinstance(value, dict):
                assert not set(value) & {"hashed_password", "api_key", "access_token", "refresh_token", "confirmation_hash", "confirmation_token", "credentials"}
                for nested in value.values():
                    check(nested)
            elif isinstance(value, list):
                for nested in value:
                    check(nested)
        check(response.json())
    assert not any(statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
    after = [(await db_session.execute(select(func.count()).select_from(model))).scalar() for model in tables]
    assert after == before


@pytest.mark.asyncio
async def test_task_query_batches_related_data_across_projects(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    projects = [Project(name=f"project-{index}", owner_id=owner.id) for index in range(12)]
    db_session.add_all(projects)
    await db_session.flush()
    db_session.add_all([Task(project_id=project.id, creator_id=owner.id, title="Batch task") for project in projects])
    await db_session.commit()
    statements = []
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
    try:
        response = await client.get(f"{BASE}/tasks", headers=auth_headers)
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 12
    assert len(statements) <= 8, f"12 projects should use batched reads, got {len(statements)} SQL statements"


@pytest.mark.asyncio
async def test_task_search_treats_sql_wildcards_literally_and_searches_all_text(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    project = Project(name="Search", owner_id=owner.id)
    db_session.add(project)
    await db_session.flush()
    tasks = [
        Task(project_id=project.id, creator_id=owner.id, title="Complete 50%_ milestone"),
        Task(project_id=project.id, creator_id=owner.id, title="Complete 50XX milestone"),
        Task(project_id=project.id, creator_id=owner.id, title="Goal match", goal="UPPER goal marker"),
        Task(project_id=project.id, creator_id=owner.id, title="Description match", description="UPPER description marker"),
    ]
    db_session.add_all(tasks)
    await db_session.commit()
    literal = await client.get(f"{BASE}/tasks", headers=auth_headers, params={"search": " 50%_ "})
    assert literal.status_code == 200, literal.text
    assert literal.json()["total"] == 1
    assert literal.json()["items"][0]["id"] == str(tasks[0].id)
    assert literal.json()["scope"]["search"] == "50%_"
    content = (await client.get(f"{BASE}/tasks", headers=auth_headers, params={"search": "upper"})).json()
    assert {row["id"] for row in content["items"]} == {str(task.id) for task in tasks[2:]}
    assert (await client.get(f"{BASE}/tasks", headers=auth_headers,
        params={"assignee_id": str(uuid.uuid4())})).json()["total"] == 0


@pytest.mark.asyncio
async def test_task_status_filter_agrees_with_display_at_start_boundary(client, auth_headers, db_session, test_user, monkeypatch):
    monkeypatch.setattr(task_service, "_now", lambda: START)
    owner, _ = test_user
    project = Project(name="Start boundary", owner_id=owner.id)
    db_session.add(project)
    await db_session.flush()
    tasks = [Task(project_id=project.id, creator_id=owner.id, title=title,
        start_date=start, status=status) for title, start, status in (
        ("Starting now", START, TaskStatus.NOT_STARTED),
        ("Starting later", START + timedelta(microseconds=1), TaskStatus.IN_PROGRESS),
        ("Completed", START + timedelta(days=1), TaskStatus.DONE),
    )]
    db_session.add_all(tasks)
    await db_session.commit()
    for status, task in zip(("in_progress", "not_started", "done"), tasks):
        response = await client.get(f"{BASE}/tasks", headers=auth_headers, params={"status": status})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 1 and data["items"][0]["id"] == str(task.id)
        assert data["items"][0]["status"] == status


@pytest.mark.asyncio
async def test_progress_naive_dates_mean_utc_and_task_project_filters_intersect(client, auth_headers, db_session, test_user):
    projects, tasks, _, events = await seed(db_session, test_user[0])
    naive = await client.get(f"{BASE}/progress", headers=auth_headers,
        params={"since": "2026-01-01T00:00:00", "until": "2026-01-01T01:00:00"})
    assert naive.status_code == 200, naive.text
    assert [row["id"] for row in naive.json()["items"]] == [str(events[0].id)]
    assert naive.json()["scope"]["since"] == "2026-01-01T00:00:00+00:00"
    assert naive.json()["scope"]["until"] == "2026-01-01T01:00:00+00:00"
    same_instant = await client.get(f"{BASE}/progress", headers=auth_headers, params={
        "since": "2026-01-01T09:00:00+09:00", "until": "2026-01-01T00:00:00Z"})
    assert same_instant.status_code == 422
    mismatch = await client.get(f"{BASE}/progress", headers=auth_headers,
        params={"project_id": str(projects[1].id), "task_id": str(tasks[0].id)})
    assert mismatch.status_code == 200, mismatch.text
    assert mismatch.json()["items"] == [] and mismatch.json()["total"] == 0


@pytest.mark.asyncio
async def test_query_account_access_matches_web_and_rejects_deactivated_accounts(client, db_session, test_user):
    _, _, member, _ = await seed(db_session, test_user[0])
    token = create_access_token({"sub": str(member.id), "role": member.role.value})
    headers = {"Authorization": f"Bearer {token}"}
    for suffix, total in (("tasks", 3), ("progress", 4)):
        response = await client.get(f"{BASE}/{suffix}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == total
    member.is_active = False
    await db_session.commit()
    for suffix in ("tasks", "progress"):
        assert (await client.get(f"{BASE}/{suffix}", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_query_timestamps_include_utc_and_preserve_deadline_instant(client, auth_headers, db_session, test_user):
    owner, _ = test_user
    _, tasks, _, events = await seed(db_session, owner)
    deadline = datetime(2026, 1, 2, 9, 30, 15, 123456, tzinfo=timezone(timedelta(hours=9)))
    instant = deadline.astimezone(timezone.utc)
    task = tasks[0]
    task.start_date = instant - timedelta(days=1)
    task.deadline = instant
    task.status = TaskStatus.DONE
    task.completed_at = task.signed_off_at = instant
    task.signed_off_by_id = owner.id
    task.created_at = task.updated_at = instant - timedelta(days=2)
    await db_session.commit()

    before = datetime.now(timezone.utc)
    response = await client.get(f"{BASE}/tasks", headers=auth_headers)
    after = datetime.now(timezone.utc)
    assert response.status_code == 200, response.text
    data = response.json()
    queried_at = datetime.fromisoformat(data["queried_at"])
    assert queried_at.utcoffset() == timedelta(0) and before <= queried_at <= after
    assert data["scope"]["timezone"] == "UTC"
    row = next(item for item in data["items"] if item["id"] == str(task.id))
    for field in ("start_date", "deadline", "completed_at", "signed_off_at", "created_at", "updated_at"):
        value = datetime.fromisoformat(row[field])
        assert value.utcoffset() == timedelta(0), field
    assert datetime.fromisoformat(row["deadline"]) == deadline
    assert row["deleted_at"] is None

    before = datetime.now(timezone.utc)
    response = await client.get(f"{BASE}/progress", headers=auth_headers)
    after = datetime.now(timezone.utc)
    assert response.status_code == 200, response.text
    data = response.json()
    queried_at = datetime.fromisoformat(data["queried_at"])
    assert queried_at.utcoffset() == timedelta(0) and before <= queried_at <= after
    first_event = next(item for item in data["items"] if item["id"] == str(events[0].id))
    assert datetime.fromisoformat(first_event["created_at"]) == START
