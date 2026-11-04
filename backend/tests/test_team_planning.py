"""Planning actions persist facts rather than deriving personal scores."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.task import Task
from app.models.task_event import TaskEvent, TaskEventType
from app.models.system_setting import SystemSetting
from app.models.team_planning import ReportVersion, PlanBaseline, WeekCommitment
from app.services.report_metrics import progress_rankings


async def setup_project(client, headers):
    user_id = (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]
    project = (await client.post("/api/v1/projects", headers=headers, json={"name": "Planning project"})).json()
    tasks = []
    for name in ("First", "Second", "Third"):
        response = await client.post(f"/api/v1/projects/{project['id']}/tasks", headers=headers, json={"title": name, "estimated_hours": 8, "assignee_ids": [user_id]})
        assert response.status_code == 201, response.text
        tasks.append(response.json())
    return project, tasks


@pytest.mark.asyncio
async def test_capacity_explicit_hours_and_gap(client, auth_headers, test_user):
    user, _ = test_user
    _, tasks = await setup_project(client, auth_headers)
    week = "2026-11-02"
    before = (await client.get(f"/api/v1/management/capacity?week_start={week}", headers=auth_headers)).json()
    person = next(row for row in before["users"] if row["user_id"] == str(user.id))
    assert person["available_hours"] is None
    invalid = await client.put(f"/api/v1/management/capacity?week_start={week}", headers=auth_headers, json={"user_id": str(user.id), "available_hours": -1})
    assert invalid.status_code == 422
    saved = await client.put(f"/api/v1/management/capacity?week_start={week}", headers=auth_headers, json={"user_id": str(user.id), "available_hours": 24, "note": "Meetings reserved"})
    assert saved.status_code == 200, saved.text
    for item in tasks[:2]:
        response = await client.post("/api/v1/management/allocations", headers=auth_headers, json={"task_id": item["id"], "user_id": str(user.id), "week_start": week, "hours": 16})
        assert response.status_code == 201, response.text
    result = (await client.get(f"/api/v1/management/capacity?week_start={week}", headers=auth_headers)).json()
    person = next(row for row in result["users"] if row["user_id"] == str(user.id))
    assert person["allocated_hours"] == 32
    assert person["gap_hours"] == 8
    # Re-saving the same person/task/week changes its allocation, not the task count.
    await client.post("/api/v1/management/allocations", headers=auth_headers, json={"task_id": tasks[0]["id"], "user_id": str(user.id), "week_start": week, "hours": 3})
    result = (await client.get(f"/api/v1/management/capacity?week_start={week}", headers=auth_headers)).json()
    assert len(result["allocations"]) == 2
    assert result["totals"]["allocated_hours"] == 19
    # Adding children later does not make an old parent allocation count twice.
    child = await client.post(f"/api/v1/projects/{tasks[0]['project_id']}/tasks", headers=auth_headers,
        json={"title": "split work", "parent_task_id": tasks[0]["id"], "assignee_ids": [str(user.id)]})
    assert child.status_code == 201
    result = (await client.get(f"/api/v1/management/capacity?week_start={week}", headers=auth_headers)).json()
    assert result["totals"]["allocated_hours"] == 16
    assert next(row for row in result["allocations"] if row["task_id"] == tasks[0]["id"])["excluded_from_total"]


@pytest.mark.asyncio
async def test_parent_allocations_and_dependency_cycles_rejected(client, auth_headers, test_user):
    user, _ = test_user
    project, tasks = await setup_project(client, auth_headers)
    child = await client.post(f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers, json={"title": "child", "parent_task_id": tasks[0]["id"]})
    assert child.status_code == 201
    result = await client.post("/api/v1/management/allocations", headers=auth_headers, json={"task_id": tasks[0]["id"], "user_id": str(user.id), "week_start": "2026-11-02", "hours": 8})
    assert result.status_code == 400
    for a, b in ((0, 1), (1, 2)):
        response = await client.post("/api/v1/management/dependencies", headers=auth_headers, json={"predecessor_id": tasks[a]["id"], "successor_id": tasks[b]["id"]})
        assert response.status_code == 201, response.text
    cycle = await client.post("/api/v1/management/dependencies", headers=auth_headers, json={"predecessor_id": tasks[2]["id"], "successor_id": tasks[0]["id"]})
    assert cycle.status_code == 400
    assert "cycle" in cycle.json()["detail"]
    self_edge = await client.post("/api/v1/management/dependencies", headers=auth_headers, json={"predecessor_id": tasks[0]["id"], "successor_id": tasks[0]["id"]})
    assert self_edge.status_code == 400
    listed = (await client.get(f"/api/v1/management/dependencies?project_id={project['id']}", headers=auth_headers)).json()
    assert len(listed) == 2 and all(row["is_blocked"] for row in listed)


@pytest.mark.asyncio
async def test_milestone_membership_and_immutable_baseline(client, auth_headers, test_user, db_session):
    user, _ = test_user
    project, tasks = await setup_project(client, auth_headers)
    other, others = await setup_project(client, auth_headers)
    bad = await client.post("/api/v1/management/milestones", headers=auth_headers, json={"project_id": project["id"], "name": "Release", "owner_id": str(user.id), "due_date": "2026-11-20", "task_ids": [others[0]["id"]]})
    assert bad.status_code == 400
    good = await client.post("/api/v1/management/milestones", headers=auth_headers, json={"project_id": project["id"], "name": "Release", "owner_id": str(user.id), "due_date": "2026-11-20", "task_ids": [tasks[0]["id"]]})
    assert good.status_code == 201 and good.json()["total_tasks"] == 1
    baseline = await client.post(f"/api/v1/management/projects/{project['id']}/baseline", headers=auth_headers, json={"label": "Original promise"})
    assert baseline.status_code == 201, baseline.text
    original = baseline.json()
    changed = await client.patch(f"/api/v1/tasks/{tasks[0]['id']}", headers=auth_headers, json={"estimated_hours": 12})
    assert changed.status_code == 200, changed.text
    current = (await client.get(f"/api/v1/management/baselines?project_id={project['id']}", headers=auth_headers)).json()[0]
    item = next(row for row in current["tasks"] if row["task_id"] == tasks[0]["id"])
    assert item["baseline_hours"] == 8 and item["current_hours"] == 12 and item["changed"]
    stored = (await db_session.execute(select(PlanBaseline))).scalar_one()
    assert next(row for row in stored.snapshot_json if row["task_id"] == tasks[0]["id"])["estimated_hours"] == 8


@pytest.mark.asyncio
async def test_retrospective_action_creates_linked_owned_task(client, auth_headers, test_user):
    user, _ = test_user
    project, tasks = await setup_project(client, auth_headers)
    commitment = await client.post("/api/v1/management/commitments", headers=auth_headers, json={"task_id": tasks[0]["id"], "owner_id": str(user.id), "week_start": "2026-11-02", "expected_outcome": "Reviewed evidence"})
    assert commitment.status_code == 201, commitment.text
    retro = await client.post("/api/v1/management/retrospectives", headers=auth_headers, json={"project_id": project["id"], "week_start": "2026-11-02", "summary": "Dependency was late", "decisions": "Prepare data sooner", "actions": [{"title": "Prepare fixture data", "owner_id": str(user.id), "deadline": "2026-11-10T09:00:00Z"}]})
    assert retro.status_code == 201, retro.text
    action = retro.json()["action_tasks"][0]
    assert action["owner_id"] == str(user.id)
    actual = (await client.get(f"/api/v1/tasks/{action['task_id']}", headers=auth_headers)).json()
    assert retro.json()["id"] in actual["description"]
    assert actual["assignee_ids"] == [str(user.id)]
    governed = (await client.get(f"/api/v1/management/tasks/{action['task_id']}", headers=auth_headers)).json()
    assert governed["governance"]["owner_id"] == str(user.id)
    assert governed["governance"]["reviewer_id"] == str(user.id)
    assert governed["governance"]["acceptance_criteria"] == "Prepare fixture data"
    assert governed["governance"]["handover_accepted_at"] is None
    listed = (await client.get(f"/api/v1/management/retrospectives?project_id={project['id']}", headers=auth_headers)).json()
    assert listed[0]["action_tasks"][0]["task_id"] == action["task_id"]


@pytest.mark.asyncio
async def test_report_refresh_preserves_immutable_versions(client, auth_headers, db_session):
    project, _ = await setup_project(client, auth_headers)
    first = await client.post("/api/v1/reports/refresh", headers=auth_headers, json={"report_type": "weekly"})
    assert first.status_code == 200, first.text
    first_json = first.json()
    await client.patch(f"/api/v1/projects/{project['id']}", headers=auth_headers, json={"name": "Changed project name"})
    second = await client.post("/api/v1/reports/refresh", headers=auth_headers, json={"report_type": "weekly"})
    assert second.status_code == 200
    history = (await client.get("/api/v1/reports/history?report_type=weekly", headers=auth_headers)).json()
    assert len(history) == 2
    assert first_json["history_id"] != second.json()["history_id"]
    original = await client.get(f"/api/v1/reports/history/{first_json['history_id']}", headers=auth_headers)
    assert original.status_code == 200
    assert original.json()["report"] == first_json["report"]
    assert original.json()["report"]["project_progress_table"][0]["project_name"] == "Planning project"


def test_repeated_progress_cannot_improve_report_evaluation():
    projects = [{"name": "Project", "tasks": [{"id": "a", "title": "Delivered", "status": "done", "signed_off_at": "2026-11-03", "progress_pct": 100}, {"id": "b", "title": "Needs review", "status": "in_progress", "assignee": "A", "progress_pct": 100}]}]
    baseline = progress_rankings(projects, [], date(2026, 11, 2), date(2026, 11, 8), "old", "old")
    spam = [{"user": "A", "progress_pct": 100, "created_at": "2026-11-03"}] * 100
    assert progress_rankings(projects, spam, date(2026, 11, 2), date(2026, 11, 8), "old", "old") == baseline
    assert "Delivered" in baseline[0][0]
    assert "Needs review" in baseline[1][0]


@pytest.mark.asyncio
async def test_commitment_result_is_as_of_week_end_and_target_is_frozen(client, auth_headers, test_user, db_session):
    user, _ = test_user
    project, tasks = await setup_project(client, auth_headers)
    import uuid
    task_id = uuid.UUID(tasks[0]["id"])
    old_monday = date(2026, 1, 5)
    row = WeekCommitment(project_id=uuid.UUID(project["id"]), task_id=task_id, week_start=old_monday,
                         owner_id=user.id, expected_outcome="Original reviewed delivery", outcome_note="")
    db_session.add(row)
    db_session.add_all([
        TaskEvent(task_id=task_id, actor_id=user.id, event_type=TaskEventType.SIGNOFF,
                  created_at=datetime(2026, 1, 8, 9, tzinfo=timezone.utc)),
        TaskEvent(task_id=task_id, actor_id=user.id, event_type=TaskEventType.REOPEN,
                  created_at=datetime(2026, 1, 13, 9, tzinfo=timezone.utc)),
    ])
    await db_session.commit()
    result = (await client.get(f"/api/v1/management/commitments?project_id={project['id']}&week_start=2026-01-05", headers=auth_headers)).json()[0]
    assert result["status"] == "delivered" and result["is_locked"]
    changed = await client.patch(f"/api/v1/management/commitments/{row.id}", headers=auth_headers, json={"expected_outcome": "Changed after the fact"})
    assert changed.status_code == 400
    note = await client.patch(f"/api/v1/management/commitments/{row.id}", headers=auth_headers, json={"outcome_note": "Follow-up reopened next week"})
    assert note.status_code == 200 and note.json()["status"] == "delivered"
    assert note.json()["expected_outcome"] == "Original reviewed delivery"
    backdated = await client.post("/api/v1/management/commitments", headers=auth_headers, json={"task_id": tasks[1]["id"], "owner_id": str(user.id), "week_start": "2026-01-05", "expected_outcome": "Backdated"})
    assert backdated.status_code == 400


@pytest.mark.asyncio
async def test_unassigned_work_cannot_be_silently_allocated(client, auth_headers, test_user):
    user, _ = test_user
    project = (await client.post("/api/v1/projects", headers=auth_headers, json={"name": "Unassigned"})).json()
    item = (await client.post(f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers, json={"title": "No assignee"})).json()
    response = await client.post("/api/v1/management/allocations", headers=auth_headers, json={"task_id": item["id"], "user_id": str(user.id), "week_start": "2026-11-02", "hours": 8})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_first_new_refresh_archives_existing_legacy_cache(client, auth_headers, db_session):
    db_session.add(SystemSetting(key="report_snapshot_weekly", value_json={
        "report_type": "weekly", "report": {"summary": "Existing accepted report", "source": "rules"},
        "generated_at": "2026-10-30T12:30:00+08:00", "trigger": "schedule",
    }))
    await db_session.commit()
    refreshed = await client.post("/api/v1/reports/refresh", headers=auth_headers, json={"report_type": "weekly"})
    assert refreshed.status_code == 200
    history = (await client.get("/api/v1/reports/history?report_type=weekly", headers=auth_headers)).json()
    assert len(history) == 2
    previous = next(row for row in history if row["summary"] == "Existing accepted report")
    saved = (await client.get(f"/api/v1/reports/history/{previous['id']}", headers=auth_headers)).json()
    assert saved["report"]["summary"] == "Existing accepted report"
    again = await client.post("/api/v1/reports/refresh", headers=auth_headers, json={"report_type": "weekly"})
    assert again.status_code == 200
    assert len((await client.get("/api/v1/reports/history?report_type=weekly", headers=auth_headers)).json()) == 3


@pytest.mark.asyncio
async def test_nonadmin_cannot_email_a_forged_report_scope(client, auth_headers, db_session, monkeypatch):
    from app.services import report_service
    from app.models.project_access import ProjectAccessPolicy
    import uuid
    project, _ = await setup_project(client, auth_headers)
    created = await client.post("/api/v1/users", headers=auth_headers, json={
        "username": "report_reader", "password": "temporary-test-password", "full_name": "Report Reader", "role": "member",
    })
    assert created.status_code == 201
    login = await client.post("/api/v1/auth/login", json={"username": "report_reader", "password": "temporary-test-password"})
    member = {"Authorization": "Bearer " + login.json()["access_token"]}
    refreshed = await client.post("/api/v1/reports/refresh", headers=member, json={"report_type": "weekly"})
    assert refreshed.status_code == 200
    original = refreshed.json()
    sent = []
    monkeypatch.setattr(report_service, "send_report_email", lambda *args: sent.append(args))
    # The endpoint imports this callable, patch its actual send seam too.
    monkeypatch.setattr("app.api.reports.send_report_email", lambda *args: sent.append(args))
    forged = dict(original["report"], project_ids=[])
    response = await client.post("/api/v1/reports/send", headers=member, json={
        "report_type": "weekly", "recipients": ["test@example.test"], "report": forged,
    })
    assert response.status_code == 403 and sent == []
    db_session.add(ProjectAccessPolicy(project_id=uuid.UUID(project["id"]), visibility="private"))
    await db_session.commit()
    revoked = await client.post("/api/v1/reports/send", headers=member, json={
        "report_type": "weekly", "recipients": ["test@example.test"], "report": forged,
    })
    assert revoked.status_code == 400 and sent == []
    history = await client.post("/api/v1/reports/send", headers=member, json={
        "report_type": "weekly", "recipients": ["test@example.test"], "history_id": original["history_id"],
    })
    assert history.status_code == 404 and sent == []
