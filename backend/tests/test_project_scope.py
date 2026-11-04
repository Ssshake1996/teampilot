"""Private project data must stay private across every existing surface."""
import uuid

import pytest

from app.models.user import User
from app.utils.security import create_access_token, hash_password


async def make_actor(db, name, role="manager"):
    user = User(id=uuid.uuid4(), username=name, full_name=name, role=role,
                hashed_password=hash_password("scope-test-password"))
    db.add(user)
    await db.commit()
    return user, {"Authorization": "Bearer " + create_access_token({"sub": str(user.id), "role": role})}


@pytest.mark.asyncio
async def test_private_project_hidden_from_lists_aggregates_and_legacy_routes(client, auth_headers, db_session):
    member, member_headers = await make_actor(db_session, "scope-member")
    outsider, outsider_headers = await make_actor(db_session, "scope-outsider")
    project = await client.post("/api/v1/projects", json={"name": "Private delivery", "visibility": "private"}, headers=auth_headers)
    assert project.status_code == 201
    pid = project.json()["id"]
    assert project.json()["visibility"] == "private"
    assert (await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(member.id), "role_in_project": "member"}, headers=auth_headers)).status_code == 201
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Secret delivery", "assignee_ids": [str(member.id)], "estimated_hours": 8}, headers=auth_headers)
    assert task.status_code == 201
    tid = task.json()["id"]
    assert (await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 30, "note": "Private evidence"}, headers=member_headers)).status_code == 201
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=member_headers)).status_code == 200
    blocked_removal = await client.delete(f"/api/v1/projects/{pid}/members/{member.id}", headers=auth_headers)
    assert blocked_removal.status_code == 400
    assert "交接" in blocked_removal.json()["detail"]
    downgraded = await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(member.id), "role_in_project": "observer"}, headers=auth_headers)
    assert downgraded.status_code == 400 and "交接" in downgraded.json()["detail"]
    deactivated = await client.delete(f"/api/v1/users/{member.id}", headers=auth_headers)
    assert deactivated.status_code == 400 and "交接" in deactivated.json()["detail"]
    assert (await client.get("/api/v1/projects", headers=outsider_headers)).json()["total"] == 0
    for path in [f"/api/v1/projects/{pid}", f"/api/v1/projects/{pid}/task-tree", f"/api/v1/tasks/{tid}",
                 f"/api/v1/tasks/{tid}/progress", f"/api/v1/tasks/{tid}/data-skills", f"/api/v1/management/tasks/{tid}"]:
        assert (await client.get(path, headers=outsider_headers)).status_code == 404, path
    assert (await client.patch(f"/api/v1/tasks/{tid}", json={"title": "Stolen edit"}, headers=outsider_headers)).status_code == 404
    assert (await client.patch("/api/v1/tasks/reorder", json=[{"task_id": tid, "sort_order": 2}], headers=outsider_headers)).status_code == 404
    assert (await client.get("/api/v1/dashboard/overview", headers=outsider_headers)).json()["total_tasks"] == 0
    assert (await client.get("/api/v1/dashboard/recent-activity", headers=outsider_headers)).json() == []
    assert (await client.get("/api/v1/dashboard/project-progress", headers=outsider_headers)).json() == []
    workload = (await client.get("/api/v1/dashboard/team-workload", headers=outsider_headers)).json()
    assert all(row["assigned_tasks"] == 0 and row["workload_hours"] == 0 for row in workload)
    bundle = (await client.get(f"/api/v1/users/{member.id}/detail-bundle", headers=outsider_headers)).json()
    assert bundle["tasks"] == [] and bundle["workload"]["total_tasks"] == 0
    assert (await client.get(f"/api/v1/management/projects/{pid}/access", headers=outsider_headers)).status_code == 404


@pytest.mark.asyncio
async def test_observer_read_only_even_when_global_role_can_edit(client, auth_headers, db_session):
    user, headers = await make_actor(db_session, "scope-observer")
    pid = (await client.post("/api/v1/projects", json={"name": "Observer project", "visibility": "private"}, headers=auth_headers)).json()["id"]
    await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(user.id), "role_in_project": "observer"}, headers=auth_headers)
    tid = (await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Visible task"}, headers=auth_headers)).json()["id"]
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=headers)).status_code == 200
    access = (await client.get(f"/api/v1/management/projects/{pid}/access", headers=headers)).json()
    assert access["can_write"] is False and access["can_manage"] is False
    assert (await client.patch(f"/api/v1/tasks/{tid}", json={"title": "Denied"}, headers=headers)).status_code == 403
    assert (await client.post(f"/api/v1/tasks/{tid}/progress", json={"progress_pct": 40}, headers=headers)).status_code == 403
    assert (await client.patch(f"/api/v1/management/projects/{pid}/access", json={"visibility": "company"}, headers=headers)).status_code == 403
    assert (await client.delete(f"/api/v1/projects/{pid}/members/{user.id}", headers=auth_headers)).status_code == 200
    assert (await client.get(f"/api/v1/tasks/{tid}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_private_realtime_event_only_reaches_authorized_connections(client, auth_headers, test_user, db_session, monkeypatch):
    from app import database
    from app.websocket.manager import ConnectionManager
    from tests.conftest import TestSessionLocal
    member, _ = await make_actor(db_session, "ws-member")
    outsider, _ = await make_actor(db_session, "ws-outsider")
    pid = (await client.post("/api/v1/projects", json={"name": "Private realtime", "visibility": "private"}, headers=auth_headers)).json()["id"]
    await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(member.id), "role_in_project": "member"}, headers=auth_headers)

    class Socket:
        def __init__(self):
            self.messages = []

        async def send_json(self, data):
            self.messages.append(data)

    manager = ConnectionManager()
    sockets = {str(user.id): Socket() for user in [test_user[0], member, outsider]}
    manager.active_connections = {user_id: {socket} for user_id, socket in sockets.items()}
    monkeypatch.setattr(database, "async_session", TestSessionLocal)
    event = {"type": "project.changed", "data": {"project_id": pid}}
    await manager.broadcast(event)
    assert sockets[str(test_user[0].id)].messages == [event]
    assert sockets[str(member.id)].messages == [event]
    assert sockets[str(outsider.id)].messages == []


@pytest.mark.asyncio
async def test_report_cache_and_history_recheck_project_membership(client, auth_headers, db_session):
    member, member_headers = await make_actor(db_session, "report-member")
    outsider, outsider_headers = await make_actor(db_session, "report-outsider")
    pid = (await client.post("/api/v1/projects", json={"name": "Private report content", "visibility": "private"}, headers=auth_headers)).json()["id"]
    await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Private report task"}, headers=auth_headers)
    await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(member.id), "role_in_project": "member"}, headers=auth_headers)
    admin = await client.post("/api/v1/reports/refresh", json={"report_type": "weekly"}, headers=auth_headers)
    assert admin.status_code == 200
    assert (await client.get("/api/v1/reports/snapshot", params={"report_type": "weekly"}, headers=outsider_headers)).json()["report"] is None
    safe = await client.post("/api/v1/reports/refresh", json={"report_type": "weekly"}, headers=outsider_headers)
    assert safe.status_code == 200
    assert "Private report" not in safe.text
    snapshot = await client.post("/api/v1/reports/refresh", json={"report_type": "weekly"}, headers=member_headers)
    assert snapshot.status_code == 200 and "Private report" in snapshot.text
    version_id = snapshot.json()["history_id"]
    assert (await client.get(f"/api/v1/reports/history/{version_id}", headers=outsider_headers)).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{pid}/members/{member.id}", headers=auth_headers)).status_code == 200
    assert (await client.get(f"/api/v1/reports/history/{version_id}", headers=member_headers)).status_code == 404
    assert (await client.get("/api/v1/reports/snapshot", params={"report_type": "weekly"}, headers=member_headers)).json()["report"] is None


@pytest.mark.asyncio
async def test_project_leader_can_be_transferred_before_deactivation(client, auth_headers, db_session):
    owner, owner_headers = await make_actor(db_session, "departing-leader")
    successor, successor_headers = await make_actor(db_session, "successor-leader")
    pid = (await client.post("/api/v1/projects", json={"name": "Leadership handover"}, headers=owner_headers)).json()["id"]
    blocked = await client.delete(f"/api/v1/users/{owner.id}", headers=auth_headers)
    assert blocked.status_code == 400 and "移交" in blocked.json()["detail"]
    demotion = await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(owner.id), "role_in_project": "observer"}, headers=auth_headers)
    assert demotion.status_code == 400 and "移交" in demotion.json()["detail"]
    moved = await client.patch(f"/api/v1/management/projects/{pid}/access", json={"owner_id": str(successor.id)}, headers=owner_headers)
    assert moved.status_code == 200 and moved.json()["owner_id"] == str(successor.id)
    assert moved.json()["can_transfer_owner"] is False
    assert (await client.get(f"/api/v1/management/projects/{pid}/access", headers=successor_headers)).json()["can_transfer_owner"] is True
    assert (await client.delete(f"/api/v1/users/{owner.id}", headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
async def test_milestone_responsibility_requires_handover(client, auth_headers, test_user, db_session):
    member, _ = await make_actor(db_session, "milestone-owner")
    pid = (await client.post("/api/v1/projects", json={"name": "Milestone handover"}, headers=auth_headers)).json()["id"]
    await client.post(f"/api/v1/projects/{pid}/members", json={"user_id": str(member.id), "role_in_project": "member"}, headers=auth_headers)
    milestone = await client.post("/api/v1/management/milestones", json={"project_id": pid, "name": "Pending milestone",
        "owner_id": str(member.id), "due_date": "2026-12-01", "task_ids": []}, headers=auth_headers)
    assert milestone.status_code == 201
    assert (await client.delete(f"/api/v1/projects/{pid}/members/{member.id}", headers=auth_headers)).status_code == 400
    assert (await client.delete(f"/api/v1/users/{member.id}", headers=auth_headers)).status_code == 400
    moved = await client.patch(f"/api/v1/management/milestones/{milestone.json()['id']}", json={"owner_id": str(test_user[0].id)}, headers=auth_headers)
    assert moved.status_code == 200
    assert (await client.delete(f"/api/v1/projects/{pid}/members/{member.id}", headers=auth_headers)).status_code == 200
