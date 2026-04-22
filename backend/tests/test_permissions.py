"""Tests for role permission enforcement."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_member_task_create_permission_is_enforced(client: AsyncClient, auth_headers):
    await client.post("/api/v1/users", json={
        "username": "member1",
        "password": "password123",
        "full_name": "Member One",
        "role": "member",
    }, headers=auth_headers)

    login = await client.post("/api/v1/auth/login", json={
        "username": "member1",
        "password": "password123",
    })
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    project = await client.post("/api/v1/projects", json={"name": "Permission Project"}, headers=auth_headers)
    project_id = project.json()["id"]

    denied = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Denied Task"},
        headers=member_headers,
    )
    assert denied.status_code == 403

    await client.put("/api/v1/permissions/roles", json={
        "role": "member",
        "permissions": ["task.create"],
    }, headers=auth_headers)

    allowed = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Allowed Task"},
        headers=member_headers,
    )
    assert allowed.status_code == 201
    assert allowed.json()["title"] == "Allowed Task"


@pytest.mark.asyncio
async def test_daily_brief_is_visible_to_any_logged_in_user(client: AsyncClient, auth_headers):
    await client.post("/api/v1/users", json={
        "username": "member_report",
        "password": "password123",
        "full_name": "Member Report",
        "role": "member",
    }, headers=auth_headers)

    login = await client.post("/api/v1/auth/login", json={
        "username": "member_report",
        "password": "password123",
    })
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post("/api/v1/ai/daily-brief", json={}, headers=member_headers)
    assert response.status_code == 200
    assert "event: result" in response.text or "event: error" in response.text
