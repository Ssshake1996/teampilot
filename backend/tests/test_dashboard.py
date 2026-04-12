"""Tests for dashboard endpoints."""
import pytest
from httpx import AsyncClient


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
async def test_recent_activity(client: AsyncClient, auth_headers):
    """Test recent activity endpoint."""
    res = await client.get("/api/v1/dashboard/recent-activity", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
