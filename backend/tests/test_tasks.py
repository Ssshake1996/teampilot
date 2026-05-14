"""Tests for task endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_task(client: AsyncClient, auth_headers):
    """Test creating a task in a project."""
    # Create project first
    proj = await client.post("/api/v1/projects", json={"name": "Task Project"}, headers=auth_headers)
    pid = proj.json()["id"]

    res = await client.post(f"/api/v1/projects/{pid}/tasks", json={
        "title": "Test Task",
        "goal": "Reach the expected task outcome",
        "description": "Do something",
        "priority": "high",
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Test Task"
    assert data["goal"] == "Reach the expected task outcome"
    assert data["status"] == "in_progress"
    assert data["priority"] == "high"


@pytest.mark.asyncio
async def test_update_task_goal(client: AsyncClient, auth_headers):
    """Test updating task title, goal, and description."""
    proj = await client.post("/api/v1/projects", json={"name": "Task Goal Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Old Task"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.patch(f"/api/v1/tasks/{tid}", json={
        "title": "Updated Task",
        "goal": "Updated goal",
        "description": "Updated description",
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Updated Task"
    assert data["goal"] == "Updated goal"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_list_tasks(client: AsyncClient, auth_headers):
    """Test listing tasks for a project."""
    proj = await client.post("/api/v1/projects", json={"name": "List Project"}, headers=auth_headers)
    pid = proj.json()["id"]

    await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T1"}, headers=auth_headers)
    await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T2"}, headers=auth_headers)

    res = await client.get(f"/api/v1/projects/{pid}/tasks", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 2


@pytest.mark.asyncio
async def test_reorder_subtasks(client: AsyncClient, auth_headers):
    """Test reordering sibling subtasks by sort_order."""
    proj = await client.post("/api/v1/projects", json={"name": "Reorder Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    parent = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Parent"}, headers=auth_headers)
    parent_id = parent.json()["id"]

    first = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "First"}, headers=auth_headers)
    second = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "Second"}, headers=auth_headers)
    third = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "Third"}, headers=auth_headers)

    res = await client.patch("/api/v1/tasks/reorder", json=[
        {"task_id": third.json()["id"], "sort_order": 1},
        {"task_id": first.json()["id"], "sort_order": 2},
        {"task_id": second.json()["id"], "sort_order": 3},
    ], headers=auth_headers)
    assert res.status_code == 200

    subtasks = await client.get(f"/api/v1/tasks/{parent_id}/subtasks", headers=auth_headers)
    assert subtasks.status_code == 200
    assert [item["title"] for item in subtasks.json()] == ["Third", "First", "Second"]


@pytest.mark.asyncio
async def test_reorder_parent_tasks_with_children(client: AsyncClient, auth_headers):
    """Test reordering parent tasks keeps child task tree valid."""
    proj = await client.post("/api/v1/projects", json={"name": "Parent Reorder Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    first = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "First Parent"}, headers=auth_headers)
    second = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Second Parent"}, headers=auth_headers)
    child = await client.post(f"/api/v1/tasks/{first.json()['id']}/subtasks", json={"title": "First Child"}, headers=auth_headers)
    assert child.status_code == 201

    res = await client.patch("/api/v1/tasks/reorder", json=[
        {"task_id": second.json()["id"], "sort_order": 1},
        {"task_id": first.json()["id"], "sort_order": 2},
    ], headers=auth_headers)
    assert res.status_code == 200

    tree = await client.get(f"/api/v1/projects/{pid}/task-tree", headers=auth_headers)
    assert tree.status_code == 200
    assert [item["title"] for item in tree.json()] == ["Second Parent", "First Parent"]
    assert tree.json()[1]["children"][0]["title"] == "First Child"


@pytest.mark.asyncio
async def test_subtask_weights_default_to_even_split(client: AsyncClient, auth_headers):
    """New subtasks under the same parent are evenly weighted by default."""
    proj = await client.post("/api/v1/projects", json={"name": "Weight Defaults Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    parent = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Parent"}, headers=auth_headers)
    parent_id = parent.json()["id"]

    first = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "First"}, headers=auth_headers)
    assert first.status_code == 201
    second = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "Second"}, headers=auth_headers)
    assert second.status_code == 201

    subtasks = await client.get(f"/api/v1/tasks/{parent_id}/subtasks", headers=auth_headers)
    weights = sorted(round(item["weight"], 6) for item in subtasks.json())
    assert weights == [0.5, 0.5]
    assert abs(sum(item["weight"] for item in subtasks.json()) - 1) <= 0.01

    third = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "Third"}, headers=auth_headers)
    assert third.status_code == 201

    subtasks = await client.get(f"/api/v1/tasks/{parent_id}/subtasks", headers=auth_headers)
    weights = [item["weight"] for item in subtasks.json()]
    assert len(weights) == 3
    assert abs(sum(weights) - 1) <= 0.01
    assert all(abs(weight - (1 / 3)) <= 0.01 for weight in weights)


@pytest.mark.asyncio
async def test_weighted_progress_rolls_up_through_ancestors(client: AsyncClient, auth_headers):
    """Child progress changes and weight edits update parent and ancestor progress."""
    proj = await client.post("/api/v1/projects", json={"name": "Weighted Progress Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    grandparent = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Grandparent"}, headers=auth_headers)
    grandparent_id = grandparent.json()["id"]
    parent = await client.post(f"/api/v1/tasks/{grandparent_id}/subtasks", json={"title": "Parent"}, headers=auth_headers)
    parent_id = parent.json()["id"]
    first = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "First"}, headers=auth_headers)
    second = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "Second"}, headers=auth_headers)
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    weighted = await client.patch(f"/api/v1/tasks/{first_id}", json={"weight": 0.8}, headers=auth_headers)
    assert weighted.status_code == 200

    subtasks = await client.get(f"/api/v1/tasks/{parent_id}/subtasks", headers=auth_headers)
    weights = {item["id"]: item["weight"] for item in subtasks.json()}
    assert abs(weights[first_id] - 0.8) <= 0.01
    assert abs(weights[second_id] - 0.2) <= 0.01
    assert abs(sum(weights.values()) - 1) <= 0.01

    await client.post(
        f"/api/v1/tasks/{first_id}/progress",
        json={"progress_pct": 100, "note": "First done"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/tasks/{second_id}/progress",
        json={"progress_pct": 50, "note": "Second half done"},
        headers=auth_headers,
    )

    parent_res = await client.get(f"/api/v1/tasks/{parent_id}", headers=auth_headers)
    grandparent_res = await client.get(f"/api/v1/tasks/{grandparent_id}", headers=auth_headers)
    assert parent_res.json()["progress_pct"] == 90
    assert grandparent_res.json()["progress_pct"] == 90


@pytest.mark.asyncio
async def test_complete_task_sets_completed_at(client: AsyncClient, auth_headers):
    """Test that signoff after 100% progress sets completed_at."""
    proj = await client.post("/api/v1/projects", json={"name": "Complete Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Done Task"}, headers=auth_headers)
    tid = task.json()["id"]

    blocked = await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)
    assert blocked.status_code == 400

    progress = await client.post(
        "/api/v1/ai/progress-import/commit",
        json={"updates": [{"task_id": tid, "progress_pct": 100, "note": "Ready for signoff"}]},
        headers=auth_headers,
    )
    assert progress.status_code == 200
    assert progress.json()["count"] == 1

    res = await client.post(f"/api/v1/tasks/{tid}/signoff", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "done"
    assert data["completed_at"] is not None
    assert data["signed_off_by_id"] is not None


@pytest.mark.asyncio
async def test_assign_task(client: AsyncClient, auth_headers, test_user):
    """Test assigning a task to a user."""
    user, _ = test_user
    second_user = await client.post("/api/v1/auth/register", json={
        "username": "multitask",
        "password": "password123",
        "full_name": "Multi Task",
    })
    second_user_id = second_user.json()["id"]
    proj = await client.post("/api/v1/projects", json={"name": "Assign Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Assign Me"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.patch(f"/api/v1/tasks/{tid}/assign", json={
        "assignee_ids": [str(user.id), second_user_id],
    }, headers=auth_headers)
    assert res.status_code == 200
    assert set(res.json()["assignee_ids"]) == {str(user.id), second_user_id}
    assert len(res.json()["assignee_names"]) == 2


@pytest.mark.asyncio
async def test_log_progress(client: AsyncClient, auth_headers):
    """Test logging progress on a task manually."""
    proj = await client.post("/api/v1/projects", json={"name": "Progress Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Progress Task"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.post(f"/api/v1/tasks/{tid}/progress", json={
        "progress_pct": 50,
        "note": "Half done",
        "hours_spent": 4.0,
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["progress_pct"] == 50
    assert data["note"] == "Half done"


@pytest.mark.asyncio
async def test_get_progress_history(client: AsyncClient, auth_headers):
    """Test retrieving progress history."""
    proj = await client.post("/api/v1/projects", json={"name": "History Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "History Task"}, headers=auth_headers)
    tid = task.json()["id"]

    first = await client.post(
        "/api/v1/ai/progress-import/commit",
        json={"updates": [{"task_id": tid, "progress_pct": 30, "note": "Started"}]},
        headers=auth_headers,
    )
    second = await client.post(
        "/api/v1/ai/progress-import/commit",
        json={"updates": [{"task_id": tid, "progress_pct": 80, "note": "Almost done"}]},
        headers=auth_headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200

    res = await client.get(f"/api/v1/tasks/{tid}/progress", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 2


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient, auth_headers):
    """Test deleting a task."""
    proj = await client.post("/api/v1/projects", json={"name": "Delete Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Delete Me"}, headers=auth_headers)
    tid = task.json()["id"]

    res = await client.delete(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert res.status_code == 200

    # Verify deleted
    get_res = await client.get(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_parent_task_cascades_to_subtasks_and_restore(client: AsyncClient, auth_headers):
    proj = await client.post("/api/v1/projects", json={"name": "Cascade Delete Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    parent = await client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Parent Task", "description": "Parent description"},
        headers=auth_headers,
    )
    parent_id = parent.json()["id"]
    child = await client.post(
        f"/api/v1/tasks/{parent_id}/subtasks",
        json={"title": "Child Task", "description": "Child description"},
        headers=auth_headers,
    )
    child_id = child.json()["id"]

    delete_res = await client.delete(f"/api/v1/tasks/{parent_id}", headers=auth_headers)
    assert delete_res.status_code == 200

    list_res = await client.get(f"/api/v1/projects/{pid}/tasks", headers=auth_headers)
    items = {item["id"]: item for item in list_res.json()["items"]}
    assert items[parent_id]["is_deleted"] is True
    assert items[child_id]["is_deleted"] is True

    restore_res = await client.post(f"/api/v1/tasks/{parent_id}/restore", headers=auth_headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["is_deleted"] is False

    list_res = await client.get(f"/api/v1/projects/{pid}/tasks", headers=auth_headers)
    items = {item["id"]: item for item in list_res.json()["items"]}
    assert items[parent_id]["is_deleted"] is False
    assert items[child_id]["is_deleted"] is False


@pytest.mark.asyncio
async def test_restore_subtask_blocked_when_parent_deleted(client: AsyncClient, auth_headers):
    proj = await client.post("/api/v1/projects", json={"name": "Restore Rule Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    parent = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Parent"}, headers=auth_headers)
    parent_id = parent.json()["id"]
    child = await client.post(f"/api/v1/tasks/{parent_id}/subtasks", json={"title": "Child"}, headers=auth_headers)
    child_id = child.json()["id"]

    delete_res = await client.delete(f"/api/v1/tasks/{parent_id}", headers=auth_headers)
    assert delete_res.status_code == 200

    restore_res = await client.post(f"/api/v1/tasks/{child_id}/restore", headers=auth_headers)
    assert restore_res.status_code == 400
    assert "Restore the parent task first" in restore_res.json()["detail"]


@pytest.mark.asyncio
async def test_deleted_task_cannot_accept_progress_import_updates(client: AsyncClient, auth_headers):
    proj = await client.post("/api/v1/projects", json={"name": "Deleted Progress Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Deleted Task"}, headers=auth_headers)
    tid = task.json()["id"]

    delete_res = await client.delete(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert delete_res.status_code == 200

    progress_res = await client.post(
        "/api/v1/ai/progress-import/commit",
        json={"updates": [{"task_id": tid, "progress_pct": 10, "note": "Should fail"}]},
        headers=auth_headers,
    )
    assert progress_res.status_code == 400
    assert progress_res.json()["detail"] == "Deleted tasks cannot accept progress updates."


@pytest.mark.asyncio
async def test_deleted_task_cannot_log_progress_manually(client: AsyncClient, auth_headers):
    proj = await client.post("/api/v1/projects", json={"name": "Deleted Manual Progress Project"}, headers=auth_headers)
    pid = proj.json()["id"]
    task = await client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Deleted Manual Task"}, headers=auth_headers)
    tid = task.json()["id"]

    delete_res = await client.delete(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert delete_res.status_code == 200

    progress_res = await client.post(
        f"/api/v1/tasks/{tid}/progress",
        json={"progress_pct": 10, "note": "Should fail"},
        headers=auth_headers,
    )
    assert progress_res.status_code == 400
    assert progress_res.json()["detail"] == "Deleted tasks cannot accept progress updates."
