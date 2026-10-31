import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.dsh_draft import DshDraft
from app.models.task_event import TaskEvent
from app.services.dsh_service import now

BASE = "/api/v1/integrations/dsh"


async def progress_draft(client, headers):
    project = (await client.post("/api/v1/projects", headers=headers, json={"name": "DSH test"})).json()
    task = (await client.post(f"/api/v1/projects/{project['id']}/tasks", headers=headers, json={"title": "leaf"})).json()
    context = (await client.get(f"{BASE}/projects/{project['id']}/context", headers=headers)).json()
    response = await client.post(f"{BASE}/drafts", headers=headers, json={"payload": {
        "kind": "progress", "project_id": project["id"], "revision": context["revision"],
        "updates": [{"task_id": task["id"], "progress_pct": 60, "note": "from DSH"}]}})
    assert response.status_code == 201, response.text
    return response.json(), task


@pytest.mark.asyncio
async def test_explicit_approval_idempotent_commit(client, auth_headers, db_session):
    draft, task = await progress_draft(client, auth_headers)
    assert "confirmation_hash" not in draft
    assert draft["approval_expires_at"] is None
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers,
        json={"confirmation_token": "0" * 64})).status_code == 403
    approval = (await client.post(f"{BASE}/drafts/{draft['id']}/approve", headers=auth_headers,
        json={"payload_hash": draft["payload_hash"]})).json()
    reviewed = (await client.get(f"{BASE}/drafts/{draft['id']}", headers=auth_headers)).json()
    assert reviewed["approval_expires_at"].endswith("Z") or reviewed["approval_expires_at"].endswith("+00:00")
    from datetime import datetime
    expiry = datetime.fromisoformat(reviewed["approval_expires_at"].replace("Z", "+00:00"))
    assert timedelta(minutes=4) < expiry - now() <= timedelta(minutes=5)
    assert "confirmation_hash" not in reviewed and "confirmation_token" not in reviewed
    for _ in range(2):
        response = await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=approval | {"state": "approved"})
        # Only the private token is accepted; no client-controlled state.
        assert response.status_code == 422
        response = await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers,
            json={"confirmation_token": approval["confirmation_token"]})
        assert response.status_code == 200, response.text
    events = (await db_session.execute(select(TaskEvent).where(TaskEvent.task_id == uuid.UUID(task["id"])))) .scalars().all()
    assert len(events) == 1
    assert (await client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers)).json()["progress_pct"] == 60


@pytest.mark.asyncio
async def test_changed_project_requires_new_draft(client, auth_headers):
    draft, task = await progress_draft(client, auth_headers)
    approval = (await client.post(f"{BASE}/drafts/{draft['id']}/approve", headers=auth_headers,
        json={"payload_hash": draft["payload_hash"]})).json()
    await client.post(f"/api/v1/tasks/{task['id']}/progress", headers=auth_headers, json={"progress_pct": 20})
    response = await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers,
        json={"confirmation_token": approval["confirmation_token"]})
    assert response.status_code == 409
    assert (await client.get(f"{BASE}/drafts/{draft['id']}", headers=auth_headers)).json()["state"] == "approved"


@pytest.mark.asyncio
async def test_hash_expiry_cancel_and_isolation(client, auth_headers, db_session):
    draft, _ = await progress_draft(client, auth_headers)
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/approve", headers=auth_headers,
        json={"payload_hash": "0" * 64})).status_code == 409
    row = await db_session.get(DshDraft, uuid.UUID(draft["id"]))
    row.expires_at = now() - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/approve", headers=auth_headers,
        json={"payload_hash": draft["payload_hash"]})).status_code == 409
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/cancel", headers=auth_headers)).status_code == 200
    assert (await client.get(f"{BASE}/drafts/{uuid.uuid4()}", headers=auth_headers)).status_code == 404
    assert (await client.get(f"{BASE}/drafts")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_project_plan_tree_weights_and_no_auto_signoff(client, auth_headers):
    response = await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": {
        "kind": "project_plan", "name": "native plan", "tasks": [{"title": "parent", "children": [
            {"title": "a"}, {"title": "b"}, {"title": "c"}]}]}})
    assert response.status_code == 201, response.text
    draft = response.json()
    approval = (await client.post(f"{BASE}/drafts/{draft['id']}/approve", headers=auth_headers,
        json={"payload_hash": draft["payload_hash"]})).json()
    result = (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers,
        json={"confirmation_token": approval["confirmation_token"]})).json()
    tasks = (await client.get(f"/api/v1/projects/{result['project_id']}/tasks", headers=auth_headers)).json()["items"]
    assert len(tasks) == 4
    assert abs(sum(task["weight"] for task in tasks if task["parent_task_id"]) - 1) < 0.00001
    assert all(task["signed_off_at"] is None for task in tasks)


@pytest.mark.asyncio
async def test_unknown_and_nonfinite_payloads_rejected(client, auth_headers):
    for extra in [{"status": "done"}, {"estimated_hours": -1}]:
        response = await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": {
            "kind": "project_plan", "name": "invalid", "tasks": [{"title": "task", **extra}]}})
        assert response.status_code == 422


async def approve_draft(client, headers, draft):
    response = await client.post(f"{BASE}/drafts/{draft['id']}/approve", headers=headers,
        json={"payload_hash": draft["payload_hash"]})
    assert response.status_code == 200, response.text
    return {"confirmation_token": response.json()["confirmation_token"]}


@pytest.mark.asyncio
async def test_drafts_are_private_even_to_other_admin(client, auth_headers, db_session):
    from app.models.user import User, UserRole
    from app.utils.security import create_access_token, hash_password
    draft, _ = await progress_draft(client, auth_headers)
    other = User(username="other", full_name="Other", role=UserRole.ADMIN, hashed_password=hash_password("password"))
    db_session.add(other)
    await db_session.commit()
    headers = {"Authorization": "Bearer " + create_access_token({"sub": str(other.id), "role": "admin"})}
    assert (await client.get(f"{BASE}/drafts", headers=headers)).json()["items"] == []
    assert (await client.get(f"{BASE}/drafts/{draft['id']}", headers=headers)).status_code == 404
    token = await approve_draft(client, auth_headers, draft)
    for action, body in [("approve", {"payload_hash": draft["payload_hash"]}), ("commit", token), ("cancel", None)]:
        response = await client.post(f"{BASE}/drafts/{draft['id']}/{action}", headers=headers, json=body)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_permissions_rechecked_after_approval(client, auth_headers, test_user, db_session):
    from app.models.user import UserRole
    response = await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": {
        "kind": "project_plan", "name": "blocked", "tasks": [{"title": "a"}]}})
    draft = response.json()
    token = await approve_draft(client, auth_headers, draft)
    user, _ = test_user
    user.role = UserRole.MEMBER
    await db_session.commit()
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=token)).status_code == 403
    assert (await client.get(f"{BASE}/drafts/{draft['id']}", headers=auth_headers)).json()["state"] == "approved"
    assert (await client.get("/api/v1/projects", headers=auth_headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_task_create_reopens_signed_parent_and_balances_weights(client, auth_headers):
    draft, parent = await progress_draft(client, auth_headers)
    await client.post(f"{BASE}/drafts/{draft['id']}/cancel", headers=auth_headers)
    await client.post(f"/api/v1/tasks/{parent['id']}/progress", headers=auth_headers, json={"progress_pct": 100})
    assert (await client.post(f"/api/v1/tasks/{parent['id']}/signoff", headers=auth_headers)).status_code == 200
    context = (await client.get(f"{BASE}/projects/{parent['project_id']}/context", headers=auth_headers)).json()
    response = await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": {
        "kind": "task_create", "project_id": parent["project_id"], "revision": context["revision"],
        "parent_task_id": parent["id"], "tasks": [{"title": title} for title in ("a", "b", "c")]}})
    assert response.status_code == 201, response.text
    draft = response.json()
    token = await approve_draft(client, auth_headers, draft)
    response = await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=token)
    assert response.status_code == 200, response.text
    tasks = (await client.get(f"/api/v1/projects/{parent['project_id']}/tasks", headers=auth_headers)).json()["items"]
    children = [item for item in tasks if item["parent_task_id"] == parent["id"]]
    assert len(children) == 3 and abs(sum(item["weight"] for item in children) - 1) < 0.00001
    updated = next(item for item in tasks if item["id"] == parent["id"])
    assert updated["signed_off_at"] is None and updated["progress_pct"] == 0


@pytest.mark.asyncio
async def test_partial_task_update_preserves_unspecified_fields(client, auth_headers, test_user):
    _, task = await progress_draft(client, auth_headers)
    context = (await client.get(f"{BASE}/projects/{task['project_id']}/context", headers=auth_headers)).json()
    payload = {"kind": "task_update", "project_id": task["project_id"], "revision": context["revision"],
        "task_id": task["id"], "patch": {"assignee_ids": [str(test_user[0].id)], "estimated_hours": 4}}
    draft = (await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": payload})).json()
    assert draft["preview"]["items"][0]["before"]["assignee_ids"] == []
    assert draft["preview"]["display_names"] == {str(test_user[0].id): test_user[0].full_name}
    assert draft["preview"]["project_name"] == "DSH test"
    assert draft["payload"]["patch"]["assignee_ids"] == [str(test_user[0].id)]
    token = await approve_draft(client, auth_headers, draft)
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=token)).status_code == 200
    updated = (await client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers)).json()
    assert updated["title"] == "leaf" and updated["estimated_hours"] == 4
    assert updated["assignee_ids"] == [str(test_user[0].id)]
    for patch in [{}, {"title": None}, {"status": "done"}]:
        assert (await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": payload | {"patch": patch}})).status_code == 422


@pytest.mark.asyncio
async def test_batch_failure_rolls_back_every_write(client, auth_headers, monkeypatch, db_session):
    from app.services import task_service
    draft, task = await progress_draft(client, auth_headers)
    project_id = task["project_id"]
    second = (await client.post(f"/api/v1/projects/{project_id}/tasks", headers=auth_headers, json={"title": "second"})).json()
    context = (await client.get(f"{BASE}/projects/{project_id}/context", headers=auth_headers)).json()
    draft = (await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": {
        "kind": "progress", "project_id": project_id, "revision": context["revision"],
        "updates": [{"task_id": item["id"], "progress_pct": 70} for item in [task, second]]}})).json()
    token = await approve_draft(client, auth_headers, draft)
    original = task_service.log_progress
    async def fail_second(db, task_id, *args, **kwargs):
        if str(task_id) == second["id"]:
            raise ValueError("Injected failure on second write")
        return await original(db, task_id, *args, **kwargs)
    monkeypatch.setattr(task_service, "log_progress", fail_second)
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=token)).status_code == 400
    assert (await client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers)).json()["progress_pct"] == 0
    assert (await client.get(f"{BASE}/drafts/{draft['id']}", headers=auth_headers)).json()["state"] == "approved"
    assert (await db_session.execute(select(TaskEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_expired_or_cancelled_approval_cannot_commit(client, auth_headers, db_session):
    draft, _ = await progress_draft(client, auth_headers)
    token = await approve_draft(client, auth_headers, draft)
    row = await db_session.get(DshDraft, uuid.UUID(draft["id"]))
    row.approval_expires_at = now() - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=token)).status_code == 409
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/cancel", headers=auth_headers)).status_code == 200
    assert (await client.post(f"{BASE}/drafts/{draft['id']}/commit", headers=auth_headers, json=token)).status_code == 403


@pytest.mark.asyncio
async def test_context_pagination_and_foreign_task_rejected(client, auth_headers):
    _, task = await progress_draft(client, auth_headers)
    _, foreign = await progress_draft(client, auth_headers)
    context = (await client.get(f"{BASE}/projects/{task['project_id']}/context?page=2&page_size=1", headers=auth_headers)).json()
    assert context["truncated"] and context["tasks"] == [] and context["total"] == 1
    assert (await client.get(f"{BASE}/projects/{task['project_id']}/context?page_size=101", headers=auth_headers)).status_code == 422
    response = await client.post(f"{BASE}/drafts", headers=auth_headers, json={"payload": {
        "kind": "progress", "project_id": task["project_id"], "revision": context["revision"],
        "updates": [{"task_id": foreign["id"], "progress_pct": 10}]}})
    assert response.status_code == 400
