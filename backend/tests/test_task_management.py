"""Management workflows are scoped, persistent and cannot bypass evidence review."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import select

from app.models.assignment import Assignment
from app.models.task_management import TaskChange


async def member(client, auth_headers, username):
    created = await client.post("/api/v1/users", headers=auth_headers, json={
        "username": username, "password": "test-only-password", "full_name": username, "role": "member",
    })
    assert created.status_code == 201, created.text
    login = await client.post("/api/v1/auth/login", json={"username": username, "password": "test-only-password"})
    return created.json()["id"], {"Authorization": "Bearer " + login.json()["access_token"]}


async def setup_task(client, auth_headers, test_user):
    project = await client.post("/api/v1/projects", headers=auth_headers, json={"name": "Managed delivery"})
    task = await client.post(f"/api/v1/projects/{project.json()['id']}/tasks", headers=auth_headers,
                            json={"title": "Deliver checked evidence", "assignee_ids": [str(test_user[0].id)]})
    assert task.status_code == 201, task.text
    return project.json()["id"], task.json()["id"]


async def configure(client, auth_headers, task_id, owner_id, reviewer_id, collaborators=None):
    response = await client.put(f"/api/v1/management/tasks/{task_id}/responsibility", headers=auth_headers, json={
        "owner_id": str(owner_id), "reviewer_id": reviewer_id, "collaborator_ids": collaborators or [],
        "acceptance_criteria": "The delivered report contains verified results and source evidence.",
        "change_reason": "Agree delivery ownership and review responsibilities",
    })
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_designated_reviewer_requires_handover_evidence_and_full_progress(client, auth_headers, test_user):
    project_id, task_id = await setup_task(client, auth_headers, test_user)
    reviewer_id, reviewer = await member(client, auth_headers, "designated-reviewer")
    detail = (await client.get(f"/api/v1/management/tasks/{task_id}", headers=auth_headers)).json()
    assert detail["needs_owner"] and detail["governance"] is None
    detail = await configure(client, auth_headers, task_id, test_user[0].id, reviewer_id)
    assert detail["governance"]["handover_accepted_at"] is None
    base = f"/api/v1/management/tasks/{task_id}"
    assert (await client.put(base + "/delivery", headers=auth_headers, json={"deliverable_note": "Verified report"})).status_code == 400
    assert (await client.post(base + "/handover/accept", headers=reviewer, json={})).status_code == 403
    assert (await client.post(base + "/handover/accept", headers=auth_headers, json={})).status_code == 200
    assert (await client.put(base + "/delivery", headers=auth_headers, json={})).status_code == 400
    evidence = await client.put(base + "/delivery", headers=auth_headers, json={"deliverable_url": "https://example.test/results"})
    assert evidence.status_code == 200
    assert evidence.json()["governance"]["review_status"] == "submitted"
    assert (await client.post(base + "/review", headers=reviewer, json={"decision": "accept"})).status_code == 400
    await client.post(f"/api/v1/tasks/{task_id}/progress", headers=auth_headers, json={"progress_pct": 100})
    # Even a global administrator cannot bypass a configured designated reviewer.
    assert (await client.post(f"/api/v1/tasks/{task_id}/signoff", headers=auth_headers)).status_code == 400
    assert (await client.post(base + "/review", headers=reviewer, json={"decision": "return"})).status_code == 400
    returned = await client.post(base + "/review", headers=reviewer, json={"decision": "return", "note": "Missing result explanation"})
    assert returned.json()["governance"]["review_status"] == "changes_requested"
    await client.put(base + "/delivery", headers=auth_headers, json={"deliverable_note": "Added checked result explanation"})
    accepted = await client.post(base + "/review", headers=reviewer, json={"decision": "accept", "note": "All acceptance items verified"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["task"]["status"] == "done"
    assert accepted.json()["task"]["signed_off_by_id"] == reviewer_id
    audit = await client.get(f"/api/v1/tasks/{task_id}/audit", headers=auth_headers)
    assert audit.json()["items"][0]["event_type"] == "signoff"
    # Lower progress reopens the task and invalidates its previous acceptance.
    await client.post(f"/api/v1/tasks/{task_id}/progress", headers=auth_headers, json={"progress_pct": 90})
    reopened = (await client.get(base, headers=auth_headers)).json()
    assert reopened["governance"]["review_status"] == "not_submitted"


@pytest.mark.asyncio
async def test_responsibility_handover_cannot_be_silently_reassigned(client, auth_headers, test_user, db_session):
    _, task_id = await setup_task(client, auth_headers, test_user)
    next_owner_id, next_owner = await member(client, auth_headers, "new-owner")
    reviewer_id, reviewer = await member(client, auth_headers, "other-reviewer")
    await configure(client, auth_headers, task_id, test_user[0].id, reviewer_id, [next_owner_id])
    base = f"/api/v1/management/tasks/{task_id}"
    await client.post(base + "/handover/accept", headers=auth_headers, json={})
    denied = await client.patch(f"/api/v1/tasks/{task_id}/assign", headers=auth_headers,
                               json={"assignee_ids": [next_owner_id], "change_reason": "Trying to bypass handover"})
    assert denied.status_code == 400
    detail = await configure(client, auth_headers, task_id, next_owner_id, reviewer_id, [str(test_user[0].id)])
    assert detail["governance"]["handover_accepted_at"] is None
    assert (await client.post(base + "/handover/accept", headers=auth_headers, json={})).status_code == 403
    assert (await client.post(base + "/handover/accept", headers=next_owner, json={"note": "Received prior work and risks"})).status_code == 200
    rows = (await db_session.execute(select(Assignment).where(Assignment.task_id == uuid.UUID(task_id)))).scalars().all()
    assert {str(row.user_id): row.role for row in rows}[next_owner_id] == "owner"


@pytest.mark.asyncio
async def test_persistent_issue_must_be_resolved_and_is_scoped_to_task(client, auth_headers, test_user):
    project_id, task_id = await setup_task(client, auth_headers, test_user)
    issue_owner_id, issue_owner = await member(client, auth_headers, "issue-owner")
    _, outsider = await member(client, auth_headers, "unrelated-member")
    base = f"/api/v1/management/tasks/{task_id}"
    created = await client.post(base + "/issues", headers=auth_headers, json={
        "title": "Waiting for API access", "reason": "Access has not been granted", "owner_id": issue_owner_id,
        "next_action": "Coordinate with the service owner", "due_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    })
    assert created.status_code == 201, created.text
    issue_id = created.json()["issues"][0]["id"]
    # No new progress is needed for an old unresolved blocker to remain present.
    detail = (await client.get(base, headers=auth_headers)).json()
    assert detail["issues"][0]["state"] == "open" and detail["issues"][0]["is_overdue"]
    assert detail["issues"][0]["escalation_owner_id"] == str(test_user[0].id)
    await client.post(f"/api/v1/tasks/{task_id}/progress", headers=auth_headers, json={"progress_pct": 100})
    assert (await client.post(f"/api/v1/tasks/{task_id}/signoff", headers=auth_headers)).status_code == 400
    assert (await client.patch(base + "/issues/" + issue_id, headers=outsider, json={"next_action": "Overwrite"})).status_code == 403
    assert (await client.patch(base + "/issues/" + issue_id, headers=issue_owner, json={"state": "resolved"})).status_code == 400
    other = await client.post(f"/api/v1/projects/{project_id}/tasks", headers=auth_headers, json={"title": "Other task"})
    wrong_scope = await client.patch(f"/api/v1/management/tasks/{other.json()['id']}/issues/{issue_id}", headers=auth_headers,
                                     json={"state": "resolved", "resolution": "Wrong task"})
    assert wrong_scope.status_code == 404
    resolved = await client.patch(base + "/issues/" + issue_id, headers=issue_owner,
                                  json={"state": "resolved", "resolution": "Access granted and tested"})
    assert resolved.status_code == 200
    assert resolved.json()["issues"][0]["resolved_at"]
    assert not resolved.json()["issues"][0]["is_overdue"]


@pytest.mark.asyncio
async def test_reopening_resolved_issue_invalidates_completed_task_and_ancestors(client, auth_headers, test_user):
    project_id, parent_id = await setup_task(client, auth_headers, test_user)
    created = await client.post(f"/api/v1/projects/{project_id}/tasks", headers=auth_headers, json={
        "title": "Checked child delivery", "parent_task_id": parent_id, "assignee_ids": [str(test_user[0].id)],
    })
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    bases = {item: f"/api/v1/management/tasks/{item}" for item in (task_id, parent_id)}
    for item, base in bases.items():
        await configure(client, auth_headers, item, test_user[0].id, str(test_user[0].id))
        accepted = await client.post(base + "/handover/accept", headers=auth_headers, json={})
        assert accepted.status_code == 200, accepted.text

    issue_response = await client.post(bases[task_id] + "/issues", headers=auth_headers, json={
        "title": "Delivery access interrupted", "reason": "The service is unavailable", "owner_id": str(test_user[0].id),
        "next_action": "Restore and verify access", "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    })
    assert issue_response.status_code == 201, issue_response.text
    issue_path = bases[task_id] + "/issues/" + issue_response.json()["issues"][0]["id"]
    resolved = await client.patch(issue_path, headers=auth_headers,
                                  json={"state": "resolved", "resolution": "Access restored and checked"})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["issues"][0]["resolved_at"]
    assert resolved.json()["issues"][0]["resolution"] == "Access restored and checked"
    progress = await client.post(f"/api/v1/tasks/{task_id}/progress", headers=auth_headers, json={"progress_pct": 100})
    assert progress.status_code == 201, progress.text

    completed = {}
    for item, base in bases.items():
        submitted = await client.put(base + "/delivery", headers=auth_headers, json={"deliverable_note": "Verified delivery evidence"})
        assert submitted.status_code == 200, submitted.text
        accepted = await client.post(base + "/review", headers=auth_headers,
                                    json={"decision": "accept", "note": "All delivery criteria checked"})
        assert accepted.status_code == 200, accepted.text
        completed[item] = accepted.json()
        assert completed[item]["task"]["status"] == "done"
        assert completed[item]["governance"]["review_status"] == "accepted"

    reopened_response = await client.patch(issue_path, headers=auth_headers, json={"state": "open"})
    assert reopened_response.status_code == 200, reopened_response.text
    issue = reopened_response.json()["issues"][0]
    assert issue["state"] == "open"
    assert issue["resolution"] is None and issue["resolved_at"] is None
    for item, base in bases.items():
        detail_response = await client.get(base, headers=auth_headers)
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["task"]["status"] != "done"
        assert detail["task"]["completed_at"] is None
        assert detail["task"]["signed_off_at"] is None
        assert detail["task"]["signed_off_by_id"] is None
        assert detail["governance"]["review_status"] == "not_submitted"
        assert detail["governance"]["review_note"] is None
        for field in ("owner_id", "reviewer_id", "acceptance_criteria", "handover_accepted_at", "deliverable_note"):
            assert detail["governance"][field] == completed[item]["governance"][field]
        audit = await client.get(f"/api/v1/tasks/{item}/audit", headers=auth_headers)
        assert audit.status_code == 200, audit.text
        event_types = [event["event_type"] for event in audit.json()["items"]]
        assert "signoff" in event_types and "reopen" in event_types

    # The legacy signoff route must not treat this task as already completed.
    assert (await client.post(f"/api/v1/tasks/{task_id}/signoff", headers=auth_headers)).status_code == 400
    submitted = await client.put(bases[task_id] + "/delivery", headers=auth_headers,
                                 json={"deliverable_note": "Service restored and verified again"})
    assert submitted.status_code == 200, submitted.text
    blocked_review = await client.post(bases[task_id] + "/review", headers=auth_headers, json={"decision": "accept"})
    assert blocked_review.status_code == 400, blocked_review.text
    resolved_again = await client.patch(issue_path, headers=auth_headers,
                                        json={"state": "resolved", "resolution": "Access restored again and checked"})
    assert resolved_again.status_code == 200, resolved_again.text
    # Resolving the issue alone does not restore the previous acceptance.
    assert (await client.post(f"/api/v1/tasks/{task_id}/signoff", headers=auth_headers)).status_code == 400
    accepted_again = await client.post(bases[task_id] + "/review", headers=auth_headers, json={"decision": "accept"})
    assert accepted_again.status_code == 200, accepted_again.text
    assert accepted_again.json()["task"]["status"] == "done"


@pytest.mark.asyncio
async def test_plan_edits_keep_before_after_reason_and_actor(client, auth_headers, test_user, db_session):
    _, task_id = await setup_task(client, auth_headers, test_user)
    reviewer_id, _ = await member(client, auth_headers, "plan-reviewer")
    await configure(client, auth_headers, task_id, test_user[0].id, reviewer_id)
    change = {"deadline": "2027-01-10T09:00:00Z", "estimated_hours": 8}
    assert (await client.patch(f"/api/v1/tasks/{task_id}", headers=auth_headers, json=change)).status_code == 400
    updated = await client.patch(f"/api/v1/tasks/{task_id}", headers=auth_headers, json={**change, "change_reason": "Additional integration scope agreed"})
    assert updated.status_code == 200, updated.text
    details = (await client.get(f"/api/v1/management/tasks/{task_id}", headers=auth_headers)).json()
    last = details["changes"][0]
    assert last["before_json"]["deadline"] is None
    assert "2027-01-10" in last["after_json"]["deadline"]
    assert last["reason"] == "Additional integration scope agreed"
    assert last["actor_id"] == str(test_user[0].id)
    assert float(last["after_json"]["estimated_hours"]) == 8


@pytest.mark.asyncio
async def test_invalid_delivery_url_and_empty_acceptance_are_rejected(client, auth_headers, test_user):
    _, task_id = await setup_task(client, auth_headers, test_user)
    base = f"/api/v1/management/tasks/{task_id}"
    response = await client.put(base + "/responsibility", headers=auth_headers, json={
        "owner_id": str(test_user[0].id), "reviewer_id": str(test_user[0].id),
        "acceptance_criteria": "   ", "change_reason": "Initial setup",
    })
    assert response.status_code == 422
    response = await client.put(base + "/delivery", headers=auth_headers, json={"deliverable_url": "javascript:alert(1)"})
    assert response.status_code == 422
