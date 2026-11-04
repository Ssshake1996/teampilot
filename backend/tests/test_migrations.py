import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


@pytest.mark.asyncio
async def test_fresh_schema_upgrade_is_repeatable(tmp_path):
    database = tmp_path / "migration.sqlite3"
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{database.as_posix()}")
    backend = Path(__file__).resolve().parents[1]
    for _ in range(2):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("select version_num from alembic_version").fetchone()[0] == "20261104_05"
        indexes = {row[1] for row in connection.execute("pragma index_list(task_events)")}
        assert "ix_task_events_latest_progress" in indexes
        # Emulate an unversioned consolidated deployment without the newest field/index.
        connection.execute("delete from alembic_version")
        connection.execute("drop index ix_task_events_latest_progress")
        connection.execute("alter table tasks drop column weight")
        connection.execute("insert into users (id, username, hashed_password, full_name, role, is_active) values ('00000000000000000000000000000001', 'retained', 'hash', 'Retained', 'MEMBER', 1)")
        connection.execute("insert into projects (id, name, status, owner_id) values ('00000000000000000000000000000001', 'Retained project', 'ACTIVE', '00000000000000000000000000000001')")
        for i in range(1, 5):
            connection.execute("insert into tasks (id, project_id, creator_id, title, status, priority, parent_task_id, is_deleted, sort_order) values (?, ?, ?, ?, 'IN_PROGRESS', 'MEDIUM', ?, 0, 0)",
                (f'{i:032x}', '00000000000000000000000000000001', '00000000000000000000000000000001', f'Task {i}', None if i == 1 else '00000000000000000000000000000001'))
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("select username from users").fetchone()[0] == "retained"
        assert "weight" in {row[1] for row in connection.execute("pragma table_info(tasks)")}
        weights = [row[0] for row in connection.execute("select weight from tasks where parent_task_id is not null")]
        assert len(weights) == 3
        assert sum(weights) == pytest.approx(1, abs=0.000001)
        assert connection.execute("pragma integrity_check").fetchone()[0] == "ok"


@pytest.mark.asyncio
async def test_retired_draft_history_survives_existing_revision_upgrade(tmp_path):
    database = tmp_path / "existing.sqlite3"
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{database.as_posix()}")
    backend = Path(__file__).resolve().parents[1]

    def upgrade(target="head"):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", target],
            cwd=backend, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    upgrade("20261005_02")
    user_id = "10000000000000000000000000000001"
    draft_id = "20000000000000000000000000000002"
    with sqlite3.connect(database) as connection:
        connection.execute("insert into users (id, username, hashed_password, full_name, role, is_active) values (?, 'retained', 'hash', 'Retained', 'member', 1)", (user_id,))
        connection.execute("""insert into dsh_drafts
            (id, author_id, payload, payload_hash, preview, state, expires_at, confirmation_hash, approval_expires_at, result)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            draft_id, user_id, '{"kind":"progress","updates":[]}', "a" * 64,
            '{"items":[]}', "committed", "2026-01-01 00:00:00", "b" * 64,
            "2026-01-01 00:00:00", '{"status":"historical"}',
        ))
        before = connection.execute("select * from dsh_drafts where id = ?", (draft_id,)).fetchone()
        user_before = connection.execute("select * from users where id = ?", (user_id,)).fetchone()
        assert connection.execute("select version_num from alembic_version").fetchone()[0] == "20261005_02"

    upgrade()
    with sqlite3.connect(database) as connection:
        assert connection.execute("select * from dsh_drafts where id = ?", (draft_id,)).fetchone() == before
        assert connection.execute("select * from users where id = ?", (user_id,)).fetchone() == user_before
        assert connection.execute("pragma integrity_check").fetchone()[0] == "ok"


@pytest.mark.asyncio
async def test_v050_records_survive_team_management_upgrade(tmp_path):
    database = tmp_path / "v050.sqlite3"
    env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{database.as_posix()}")
    backend = Path(__file__).resolve().parents[1]

    def migrate(target):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", target], cwd=backend,
                                env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    migrate("20261005_02")
    old_tables = {"users", "projects", "tasks", "assignments", "task_events", "system_settings",
                  "skills", "user_skills", "data_connectors", "task_data_skills", "skill_runs", "dsh_drafts", "alembic_version"}
    with sqlite3.connect(database) as connection:
        # The adoption baseline uses current metadata; remove new empty tables to
        # reproduce an actual v0.5.0 schema before exercising the new revisions.
        tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
        for name in tables - old_tables:
            assert connection.execute(f'select count(*) from "{name}"').fetchone()[0] == 0
            connection.execute(f'drop table "{name}"')
        user, project, task = (f"{number:032x}" for number in (1, 2, 3))
        connection.execute("insert into users(id,username,hashed_password,full_name,role,is_active) values(?, 'legacy','hash','Legacy','member',1)", (user,))
        connection.execute("insert into projects(id,name,status,owner_id) values(?,'Existing project','ACTIVE',?)", (project, user))
        connection.execute("insert into tasks(id,project_id,creator_id,title,status,priority,weight,is_deleted,sort_order) values(?,?,?,'Existing task','IN_PROGRESS','HIGH',0.375,0,2)", (task, project, user))
        connection.execute("insert into assignments(id,project_id,task_id,user_id,kind,role) values(?,?,?,?,'TASK_ASSIGNEE','assignee')", (f"{4:032x}", project, task, user))
        connection.execute("insert into task_events(id,task_id,actor_id,event_type,progress_pct,note) values(?,?,?,'PROGRESS',43,'Retained evidence')", (f"{5:032x}", task, user))
        connection.execute("insert into system_settings(key,value_json) values('model_providers',?)", ('{"providers":[],"retained":true}',))
        before = {name: connection.execute(f'select * from "{name}"').fetchall() for name in old_tables - {"alembic_version"}}
    migrate("head")
    migrate("head")
    with sqlite3.connect(database) as connection:
        for name, records in before.items():
            assert connection.execute(f'select * from "{name}"').fetchall() == records, name
        assert connection.execute("select version_num from alembic_version").fetchone()[0] == "20261104_05"
        for name in ("task_governance", "task_issues", "task_changes", "week_capacities", "week_allocations",
                     "project_milestones", "task_dependencies", "plan_baselines", "week_commitments", "retrospectives",
                     "report_versions", "project_access_policies"):
            assert connection.execute(f'select count(*) from "{name}"').fetchone()[0] == 0
        assert connection.execute("pragma integrity_check").fetchone()[0] == "ok"
