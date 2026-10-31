import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

from app.models.task_event import TaskEvent, TaskEventType
from app.services import project_service, task_service
from tests.conftest import engine


async def project(client, headers, name="Consistency"):
    response = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


async def task(client, headers, pid, **data):
    response = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task", **data}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_creation_cannot_bypass_signoff(client, auth_headers):
    pid = await project(client, auth_headers)
    response = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Bypass", "status": "done"}, headers=auth_headers)
    assert response.status_code in (400, 422)
    assert (await client.get(f"/api/v1/projects/{pid}/tasks", headers=auth_headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_new_child_reopens_completed_ancestors_and_preserves_history(client, auth_headers, db_session):
    pid = await project(client, auth_headers)
    root = await task(client, auth_headers, pid)
    parent = await task(client, auth_headers, pid, parent_task_id=root)
    await client.post(f"/api/v1/tasks/{parent}/progress", json={"progress_pct": 100}, headers=auth_headers)
    for tid in (parent, root):
        assert (await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)).status_code == 200
    await task(client, auth_headers, pid, parent_task_id=parent)
    for tid in (parent, root):
        data = (await client.get(f"/api/v1/tasks/{tid}", headers=auth_headers)).json()
        assert data["status"] == "in_progress"
        assert data["progress_pct"] == 0
        assert data["signed_off_at"] is None
        assert data["completed_at"] is None
        events = (await db_session.execute(select(TaskEvent).where(TaskEvent.task_id == uuid.UUID(tid)))).scalars().all()
        assert sum(e.event_type == TaskEventType.SIGNOFF for e in events) == 1
        assert any(e.event_type.value == "reopen" for e in events)
        audit = (await client.get(f"/api/v1/tasks/{tid}/audit", headers=auth_headers)).json()
        assert audit["total"] == 2
        assert {entry["event_type"] for entry in audit["items"]} == {"signoff", "reopen"}
        assert (await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)).status_code == 400


@pytest.mark.asyncio
async def test_invalid_parents_are_rejected(client, auth_headers):
    first = await project(client, auth_headers, "First")
    second = await project(client, auth_headers, "Second")
    parent = await task(client, auth_headers, first)
    for invalid in (parent, str(uuid.uuid4())):
        response = await client.post(f"/api/v1/projects/{second}/tasks", json={"title": "Invalid", "parent_task_id": invalid}, headers=auth_headers)
        assert response.status_code == 400
    await client.delete(f"/api/v1/tasks/{parent}", headers=auth_headers)
    response = await client.post(f"/api/v1/projects/{first}/tasks", json={"title": "Deleted parent", "parent_task_id": parent}, headers=auth_headers)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_dashboard_uses_effective_start_date(client, auth_headers):
    pid = await project(client, auth_headers)
    tid = await task(client, auth_headers, pid, start_date=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat())
    await client.patch(f"/api/v1/tasks/{tid}", json={"start_date": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()}, headers=auth_headers)
    overview = (await client.get("/api/v1/dashboard/overview", headers=auth_headers)).json()
    assert overview["in_progress_tasks"] == 1


@pytest.mark.asyncio
async def test_detail_permission_cannot_be_bypassed(client, auth_headers, test_user):
    await client.post("/api/v1/users", json={"username": "restricted", "password": "password123", "full_name": "Restricted", "role": "member"}, headers=auth_headers)
    await client.put("/api/v1/permissions/roles", json={"role": "member", "permissions": []}, headers=auth_headers)
    login = await client.post("/api/v1/auth/login", json={"username": "restricted", "password": "password123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for suffix in ("", "/detail-bundle", "/tasks", "/workload", "/skills"):
        assert (await client.get(f"/api/v1/users/{test_user[0].id}{suffix}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_project_list_query_count_is_constant(client, auth_headers, db_session):
    for i in range(20):
        await project(client, auth_headers, f"Project {i}")
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        items, total = await project_service.list_projects(db_session, page_size=100)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert total == len(items) == 20
    assert len(statements) <= 7


@pytest.mark.asyncio
async def test_invalid_batch_is_atomic(client, auth_headers):
    pid = await project(client, auth_headers)
    parent = await task(client, auth_headers, pid)
    response = await client.post(f"/api/v1/tasks/{parent}/batch-subtasks", json=[{"title": "Valid"}, {"title": "Invalid", "status": "done"}], headers=auth_headers)
    assert response.status_code == 400
    assert (await client.get(f"/api/v1/tasks/{parent}/subtasks", headers=auth_headers)).json() == []


@pytest.mark.asyncio
async def test_progress_regression_reopens_signed_task(client, auth_headers):
    pid = await project(client, auth_headers)
    tid = await task(client, auth_headers, pid)
    await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 100}, headers=auth_headers)
    await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)
    await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 40}, headers=auth_headers)
    data = (await client.get(f"/api/v1/tasks/{tid}", headers=auth_headers)).json()
    assert data["status"] == "in_progress"
    assert data["progress_pct"] == 40


@pytest.mark.asyncio
async def test_priority_filter_is_applied_before_pagination(client, auth_headers):
    pid = await project(client, auth_headers)
    await task(client, auth_headers, pid, priority="low")
    high = await task(client, auth_headers, pid, priority="high")
    response = (await client.get(f"/api/v1/projects/{pid}/tasks?priority=high&page_size=1", headers=auth_headers)).json()
    assert response["total"] == 1
    assert response["items"][0]["id"] == high


@pytest.mark.asyncio
async def test_signed_task_list_batches_signer_names(client, auth_headers, db_session):
    pid = await project(client, auth_headers)
    for _ in range(10):
        tid = await task(client, auth_headers, pid)
        await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 100}, headers=auth_headers)
        await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        items, total = await task_service.list_tasks(db_session, uuid.UUID(pid))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert total == len(items) == 10
    assert all(item["signed_off_by_name"] for item in items)
    assert len(statements) <= 7


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_committed_request(client, auth_headers, monkeypatch):
    from app.websocket.manager import manager
    async def fail(message):
        raise RuntimeError("Simulated notification failure")
    monkeypatch.setattr(manager, "broadcast", fail)
    pid = await project(client, auth_headers)
    assert (await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
async def test_new_child_refreshes_cached_parent_after_signoff(client, auth_headers, db_session, test_user):
    from app.models.task import Task, TaskStatus
    from app.schemas.task import TaskCreate
    pid = await project(client, auth_headers)
    parent_id = await task(client, auth_headers, pid)
    cached = await db_session.get(Task, uuid.UUID(parent_id))
    assert cached.status != TaskStatus.DONE
    await client.post(f"/api/v1/tasks/{parent_id}/progress", json={"progress_pct": 100}, headers=auth_headers)
    await client.post(f"/api/v1/tasks/{parent_id}/signoff", headers=auth_headers)
    await task_service.create_task(db_session, uuid.UUID(pid), TaskCreate(title="New child", parent_task_id=uuid.UUID(parent_id)), test_user[0].id)
    await db_session.commit()
    parent = (await client.get(f"/api/v1/tasks/{parent_id}", headers=auth_headers)).json()
    assert parent["status"] == "in_progress"
    assert parent["progress_pct"] == 0
    assert parent["signed_off_at"] is None
