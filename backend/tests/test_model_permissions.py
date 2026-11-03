"""Saved roles retain delegated settings access after the feature rename."""
import pytest

from app.models.system_setting import SystemSetting
from app.permissions import ROLE_PERMISSIONS_KEY


@pytest.mark.asyncio
async def test_legacy_delegated_permission_remains_usable(client, auth_headers, db_session):
    db_session.add(SystemSetting(key=ROLE_PERMISSIONS_KEY, value_json={
        "member": ["system.connector_manage", "progress.submit"],
    }))
    await db_session.commit()
    created = await client.post("/api/v1/users", headers=auth_headers, json={
        "username": "model_manager", "password": "password123",
        "full_name": "Model Manager", "role": "member",
    })
    assert created.status_code == 201
    login = await client.post("/api/v1/auth/login", json={
        "username": "model_manager", "password": "password123",
    })
    delegated = {"Authorization": f"Bearer {login.json()['access_token']}"}
    effective = (await client.get("/api/v1/permissions/me", headers=delegated)).json()
    assert "system.model_manage" in effective["permissions"]
    assert "system.connector_manage" not in effective["permissions"]
    assert (await client.get("/api/v1/model-providers", headers=delegated)).status_code == 200
    assert (await client.get("/api/v1/data-connectors", headers=delegated)).status_code == 200
    roles = (await client.get("/api/v1/permissions/roles", headers=auth_headers)).json()
    assert roles["member"]["permissions"] == ["system.model_manage", "progress.submit"]
    original = await db_session.get(SystemSetting, ROLE_PERMISSIONS_KEY)
    assert original.value_json["member"][0] == "system.connector_manage"
