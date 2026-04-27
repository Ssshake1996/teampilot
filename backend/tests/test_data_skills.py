"""Tests for task data Skill workflow."""
import pytest
import httpx
from httpx import AsyncClient, Request, Response


@pytest.mark.asyncio
async def test_task_data_skill_run_and_adopt(client: AsyncClient, auth_headers, monkeypatch):
    project = await client.post("/api/v1/projects", json={"name": "Data Skill Project"}, headers=auth_headers)
    project_id = project.json()["id"]
    task = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": "Complete FEAT-1024 test execution",
            "description": "feature_id=FEAT-1024",
        },
        headers=auth_headers,
    )
    task_id = task.json()["id"]

    connector = await client.post(
        "/api/v1/data-connectors",
        json={
            "name": "Test Platform",
            "key": "test_platform",
            "base_url": "http://internal.test",
            "auth_type": "none",
            "auth_config_json": {},
            "headers_json": {},
            "verify_tls": False,
            "is_enabled": True,
        },
        headers=auth_headers,
    )
    assert connector.status_code == 201

    skill = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/generate",
        json={
            "natural_language": "This task data comes from Test Platform. GET /api/test/feature/{feature_id}/summary.",
            "connector_id": connector.json()["id"],
        },
        headers=auth_headers,
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]
    assert skill.json()["skill_json"]["path"] == "/api/test/feature/{feature_id}/summary"

    confirmed = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/{skill_id}/confirm",
        headers=auth_headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    original_request = httpx.AsyncClient.request

    async def fake_request(self, method, url, **kwargs):
        if not str(url).startswith("http://internal.test"):
            return await original_request(self, method, url, **kwargs)
        assert method == "GET"
        assert str(url) == "http://internal.test/api/test/feature/FEAT-1024/summary"
        return Response(
            200,
            json={
                "total_cases": 100,
                "executed_cases": 80,
                "passed_cases": 76,
                "failed_cases": 4,
                "blocked_cases": 0,
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    run = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/{skill_id}/run",
        json={"params": {}, "use_ai": False},
        headers=auth_headers,
    )
    assert run.status_code == 201
    run_data = run.json()
    assert run_data["status"] == "success"
    assert run_data["suggested_progress_pct"] == 80

    adopted = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/runs/{run_data['id']}/adopt",
        json={},
        headers=auth_headers,
    )
    assert adopted.status_code == 200
    assert adopted.json()["progress_pct"] == 80

    history = await client.get(f"/api/v1/tasks/{task_id}/progress", headers=auth_headers)
    assert history.status_code == 200
    assert history.json()[0]["progress_pct"] == 80
    assert "数据 Skill" in history.json()[0]["note"]


@pytest.mark.asyncio
async def test_task_data_skill_supports_dynamic_token_auth(client: AsyncClient, auth_headers, monkeypatch):
    project = await client.post("/api/v1/projects", json={"name": "Dynamic Auth Project"}, headers=auth_headers)
    project_id = project.json()["id"]
    task = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": "Complete FEAT-2048 test execution",
            "description": "feature_id=FEAT-2048",
        },
        headers=auth_headers,
    )
    task_id = task.json()["id"]

    connector = await client.post(
        "/api/v1/data-connectors",
        json={
            "name": "Dynamic Test Platform",
            "key": "dynamic_test_platform",
            "base_url": "http://dynamic.test",
            "auth_type": "dynamic_token",
            "auth_config_json": {
                "token_url": "/api/login",
                "method": "POST",
                "body": {"app_id": "team", "app_secret": "secret"},
                "token_path": "$.data.access_token",
                "expires_in_path": "$.data.expires_in",
                "token_prefix": "Bearer",
                "target": "header",
                "target_name": "Authorization",
                "cache_seconds": 3600,
            },
            "headers_json": {},
            "verify_tls": False,
            "is_enabled": True,
        },
        headers=auth_headers,
    )
    assert connector.status_code == 201

    skill = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/generate",
        json={
            "natural_language": "GET /api/test/feature/{feature_id}/summary.",
            "connector_id": connector.json()["id"],
        },
        headers=auth_headers,
    )
    assert skill.status_code == 201
    skill_id = skill.json()["id"]

    calls = {"login": 0, "business": 0}
    original_request = httpx.AsyncClient.request

    async def fake_request(self, method, url, **kwargs):
        url_text = str(url)
        if not url_text.startswith("http://dynamic.test"):
            return await original_request(self, method, url, **kwargs)
        if url_text == "http://dynamic.test/api/login":
            calls["login"] += 1
            assert method == "POST"
            assert kwargs.get("json") == {"app_id": "team", "app_secret": "secret"}
            return Response(
                200,
                json={"data": {"access_token": "token-abc", "expires_in": 3600}},
                request=Request(method, url),
            )
        calls["business"] += 1
        assert url_text == "http://dynamic.test/api/test/feature/FEAT-2048/summary"
        assert (kwargs.get("headers") or {}).get("Authorization") == "Bearer token-abc"
        return Response(
            200,
            json={"total_cases": 10, "executed_cases": 10, "failed_cases": 0, "blocked_cases": 0},
            request=Request(method, url),
        )

    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    first_run = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/{skill_id}/run",
        json={"params": {}, "use_ai": False},
        headers=auth_headers,
    )
    second_run = await client.post(
        f"/api/v1/tasks/{task_id}/data-skills/{skill_id}/run",
        json={"params": {}, "use_ai": False},
        headers=auth_headers,
    )

    assert first_run.status_code == 201
    assert second_run.status_code == 201
    assert first_run.json()["status"] == "success", first_run.json()
    assert second_run.json()["status"] == "success", second_run.json()
    assert first_run.json()["suggested_progress_pct"] == 100
    assert second_run.json()["suggested_progress_pct"] == 100
    assert calls == {"login": 1, "business": 2}
