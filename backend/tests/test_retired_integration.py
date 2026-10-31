"""Removing an optional integration must not disable independent business APIs."""
import uuid

import pytest

from app.main import app
from app.models import Base


@pytest.mark.asyncio
async def test_retired_integration_routes_are_unavailable(client, auth_headers):
    project_id, draft_id = uuid.uuid4(), uuid.uuid4()
    paths = [
        ("GET", "/api/v1/integrations/dsh/account"),
        ("GET", "/api/v1/integrations/dsh/tasks"),
        ("GET", "/api/v1/integrations/dsh/progress"),
        ("GET", f"/api/v1/integrations/dsh/projects/{project_id}/context"),
        ("GET", "/api/v1/integrations/dsh/drafts"),
        ("POST", "/api/v1/integrations/dsh/drafts"),
        ("GET", f"/api/v1/integrations/dsh/drafts/{draft_id}"),
        ("POST", f"/api/v1/integrations/dsh/drafts/{draft_id}/approve"),
        ("POST", f"/api/v1/integrations/dsh/drafts/{draft_id}/commit"),
        ("POST", f"/api/v1/integrations/dsh/drafts/{draft_id}/cancel"),
    ]
    for method, path in paths:
        response = await client.request(method, path, headers=auth_headers)
        assert response.status_code == 404, (method, path, response.text)

    assert not any("/integrations/dsh" in path for path in app.openapi()["paths"])
    assert "dsh_drafts" not in Base.metadata.tables


@pytest.mark.asyncio
async def test_business_workflow_works_without_integration(client, auth_headers):
    assert (await client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 200
    project = await client.post("/api/v1/projects", headers=auth_headers,
        json={"name": "Independent project"})
    assert project.status_code == 201, project.text
    task = await client.post(f"/api/v1/projects/{project.json()['id']}/tasks", headers=auth_headers,
        json={"title": "Manual task"})
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    progress = await client.post(f"/api/v1/tasks/{task_id}/progress", headers=auth_headers,
        json={"progress_pct": 35, "note": "Submitted manually", "hours_spent": 2})
    assert progress.status_code == 201, progress.text
    current = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["progress_pct"] == 35
    assert (await client.get("/api/v1/dashboard/overview", headers=auth_headers)).status_code == 200
