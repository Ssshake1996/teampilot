"""Tests for task endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_task(client: AsyncClient, auth_headers):
    """Test creating a task in a project."""
    # Create project first
    proj = await client.post("/api/v1/projects", json={"name": "Task Project"}, headers=auth_headers)
    pid = proj.json()["id"]

    res = await client.post(f"/api/v1/projects/{pid}/tasks", json={
        "title": "Test Task",
        "description": "Do something",
        "priority": "high",
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Test Task"
    assert data["status"] == "in_progress"
    assert data["priority"] == "high"


@pytest.mark.asyncio
async def test_list_tasks(client: AsyncClient, auth_headers):
    """Test listing tasks for a project."""
    proj = await client.post("/api/v1/projects", json={"name": "List Project"}, headers=auth_headers)
    pid = proj.json()["id"]

    await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T1"}, headers=auth_headers)
    await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T2"}, headers=auth_headers)

    res = await client.get(f"/api/v1/projects/{pid}/tasks", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 2


@pytest.mark.asyncio
async def test_complete_task_sets_completed_at(client: AsyncClient, auth_headers):
    """Test that signoff after 100% progress sets completed_at."""
    proj = await client.post("/api/v1/projects", json={"name": "Complete Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Done Task"}, headers=auth_headers)
    tid = task.json()["id"]

    blocked = await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)
    assert blocked.status_code == 400

    progress = await client.post(
        f"/api/v1/tasks/{tid}/progress",
        json={"progress_pct": 100, "note": "Ready for signoff"},
        headers=auth_headers,
    )
    assert progress.status_code == 201

    res = await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "done"
    assert data["completed_at"] is not None
    assert data["signed_off_by_id"] is not None


@pytest.mark.asyncio
async def test_assign_task(client: AsyncClient, auth_headers, test_user):
    """Test assigning a task to a user."""
    user, _ = test_user
    second_user = await client.post("/api/v1/auth/register", json={
        "username": "multitask",
        "password": "password123",
        "full_name": "Multi Task",
    })
    second_user_id = second_user.json()["id"]
    proj = await client.post("/api/v1/projects", json={"name": "Assign Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Assign Me"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.patch(f"/api/v1/tasks/{tid}/assign", json={
        "assignee_ids": [str(user.id), second_user_id],
    }, headers=auth_headers)
    assert res.status_code == 200
    assert set(res.json()["assignee_ids"]) == {str(user.id), second_user_id}
    assert len(res.json()["assignee_names"]) == 2


@pytest.mark.asyncio
async def test_log_progress(client: AsyncClient, auth_headers):
    """Test logging progress on a task."""
    proj = await client.post("/api/v1/projects", json={"name": "Progress Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Progress Task"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.post(f"/api/v1/tasks/{tid}/progress", json={
        "progress_pct": 50,
        "note": "Half done",
        "hours_spent": 4.0,
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["progress_pct"] == 50
    assert data["note"] == "Half done"


@pytest.mark.asyncio
async def test_get_progress_history(client: AsyncClient, auth_headers):
    """Test retrieving progress history."""
    proj = await client.post("/api/v1/projects", json={"name": "History Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "History Task"}, headers=auth_headers)
    tid = task.json()["id"]

    await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 30, "note": "Started"}, headers=auth_headers)
    await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 80, "note": "Almost done"}, headers=auth_headers)

    res = await client.get(f"/api/v1/tasks/{tid}/progress", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 2


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient, auth_headers):
    """Test deleting a task."""
    proj = await client.post("/api/v1/projects", json={"name": "Delete Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Delete Me"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.delete(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert res.status_code == 200

    # Verify deleted
    get_res = await client.get(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert get_res.status_code == 404
