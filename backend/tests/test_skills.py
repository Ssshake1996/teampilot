"""Tests for skill endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_skill(client: AsyncClient, auth_headers):
    """Test creating a skill (admin only)."""
    res = await client.post("/api/v1/skills", json={
        "name": "Python",
        "category": "backend",
        "description": "Python programming",
    }, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["name"] == "Python"
    assert res.json()["category"] == "backend"


@pytest.mark.asyncio
async def test_list_skills(client: AsyncClient, auth_headers):
    """Test listing skills."""
    await client.post("/api/v1/skills", json={"name": "Vue.js", "category": "frontend"}, headers=auth_headers)
    await client.post("/api/v1/skills", json={"name": "FastAPI", "category": "backend"}, headers=auth_headers)

    res = await client.get("/api/v1/skills", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


@pytest.mark.asyncio
async def test_list_skills_by_category(client: AsyncClient, auth_headers):
    """Test filtering skills by category."""
    await client.post("/api/v1/skills", json={"name": "React", "category": "frontend"}, headers=auth_headers)
    await client.post("/api/v1/skills", json={"name": "Django", "category": "backend"}, headers=auth_headers)

    res = await client.get("/api/v1/skills?category=frontend", headers=auth_headers)
    assert res.status_code == 200
    for skill in res.json():
        assert skill["category"] == "frontend"


@pytest.mark.asyncio
async def test_delete_skill(client: AsyncClient, auth_headers):
    """Test deleting a skill."""
    create_res = await client.post("/api/v1/skills", json={"name": "Temp Skill"}, headers=auth_headers)
    sid = create_res.json()["id"]

    res = await client.delete(f"/api/v1/skills/{sid}", headers=auth_headers)
    assert res.status_code == 200
