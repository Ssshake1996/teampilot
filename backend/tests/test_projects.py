"""Tests for project endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers):
    """Test creating a new project."""
    res = await client.post("/api/v1/projects", json={
        "name": "Test Project",
        "description": "A test project",
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Test Project"
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
    }, headers=auth_headers)
    pid = create_res.json()["id"]

    res = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Detail Project"


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers):
    """Test updating a project."""
    create_res = await client.post("/api/v1/projects", json={
        "name": "Original Name",
    }, headers=auth_headers)
    pid = create_res.json()["id"]

    res = await client.patch(f"/api/v1/projects/{pid}", json={
        "name": "Updated Name",
        "status": "active",
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Name"
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
