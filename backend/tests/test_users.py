"""Tests for user endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient, auth_headers):
    """Test listing users."""
    res = await client.get("/api/v1/users", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_users_overview_returns_people(client: AsyncClient, auth_headers):
    """Personnel overview should include user rows for the frontend list."""
    res = await client.get("/api/v1/users/overview?page=1&page_size=100", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["user"]["username"] == "testuser"
    assert "skills" in data["items"][0]
    assert "workload" in data["items"][0]
    assert "departments" in data


@pytest.mark.asyncio
async def test_get_user(client: AsyncClient, auth_headers, test_user):
    """Test getting user by id."""
    user, _ = test_user
    res = await client.get(f"/api/v1/users/{user.id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_update_user(client: AsyncClient, auth_headers, test_user):
    """Test updating user profile."""
    user, _ = test_user
    res = await client.patch(f"/api/v1/users/{user.id}", json={
        "full_name": "Updated Name",
        "bio": "Focused on backend services and project delivery.",
    }, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["full_name"] == "Updated Name"
    assert res.json()["bio"] == "Focused on backend services and project delivery."


@pytest.mark.asyncio
async def test_users_table_columns_are_current(db_session):
    """Ensure backend DB columns match the current user model contract."""
    from sqlalchemy import inspect

    columns = await db_session.run_sync(
        lambda sync_session: {
            col["name"]
            for col in inspect(sync_session.get_bind()).get_columns("users")
        }
    )

    assert "bio" in columns
    assert "email" not in columns


@pytest.mark.asyncio
async def test_get_workload(client: AsyncClient, auth_headers, test_user):
    """Test getting user workload."""
    user, _ = test_user
    res = await client.get(f"/api/v1/users/{user.id}/workload", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_tasks" in data
    assert "in_progress_tasks" in data
