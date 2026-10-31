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
        assert connection.execute("select version_num from alembic_version").fetchone()[0] == "20261005_02"
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
