"""Tests for project endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers):
    """Test creating a new project."""
    res = await client.post("/api/v1/projects", json={
        "name": "Test Project",
        "goal": "Ship the milestone on time",
        "description": "A test project",
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Test Project"
    assert data["goal"] == "Ship the milestone on time"
    assert data["status"] == "planning"
    assert data["member_count"] == 1  # owner auto-added


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers):
    """Test listing projects."""
    await client.post("/api/v1/projects", json={"name": "P1"}, headers=auth_headers)
    await client.post("/api/v1/projects", json={"name": "P2"}, headers=auth_headers)

    res = await client.get("/api/v1/projects", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers):
    """Test getting a single project."""
    create_res = await client.post("/api/v1/projects", json={
        "name": "Detail Project",
        "goal": "Keep the scope tight",
        "description": "Project detail description",
    }, headers=auth_headers)
    pid = create_res.json()["id"]

    res = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Detail Project"
    assert res.json()["goal"] == "Keep the scope tight"
    assert res.json()["description"] == "Project detail description"


@pytest.mark.asyncio
async def test_project_member_count_includes_task_assignees(client: AsyncClient, auth_headers):
    second_user = await client.post("/api/v1/auth/register", json={
        "username": "project_member_count",
        "password": "password123",
        "full_name": "Project Member Count",
    })
    second_user_id = second_user.json()["id"]

    create_res = await client.post("/api/v1/projects", json={
        "name": "Count Project",
    }, headers=auth_headers)
    pid = create_res.json()["id"]

    task_res = await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Assigned Task", "assignee_ids": [second_user_id]},
        headers=auth_headers,
    )
    assert task_res.status_code == 201

    detail_res = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["member_count"] == 2

    list_res = await client.get("/api/v1/projects", headers=auth_headers)
    assert list_res.status_code == 200
    project = next(item for item in list_res.json()["items"] if item["id"] == pid)
    assert project["member_count"] == 2


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers):
    """Test updating a project."""
    create_res = await client.post("/api/v1/projects", json={
        "name": "Original Name",
    }, headers=auth_headers)
    pid = create_res.json()["id"]

    res = await client.patch(f"/api/v1/projects/{pid}", json={
        "name": "Updated Name",
        "goal": "Updated goal",
        "status": "active",
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Name"
    assert res.json()["goal"] == "Updated goal"
    assert res.json()["status"] == "active"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers):
    """Test archiving a project."""
    create_res = await client.post("/api/v1/projects", json={
        "name": "To Delete",
    }, headers=auth_headers)
    pid = create_res.json()["id"]

    res = await client.delete(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["message"] == "Project archived"
