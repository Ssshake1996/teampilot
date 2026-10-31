"""Adopt the consolidated schema and add reopen audit support.

Existing consolidated deployments keep their records; new databases get all tables.
"""
from alembic import op
from decimal import Decimal, ROUND_DOWN
from sqlalchemy import inspect, text
import sqlalchemy as sa

from app.models import Base
from app.models.task import Task
from app.models.task_event import TaskEvent

revision = "20261005_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    Base.metadata.create_all(connection)
    columns = {column["name"] for column in inspect(connection).get_columns("tasks")}
    if "weight" not in columns:
        op.add_column("tasks", sa.Column("weight", sa.Numeric(10, 6), nullable=False, server_default="1"))
        # Backfill only deployments that did not have weights; keep existing custom weights.
        siblings = {}
        rows = connection.execute(sa.select(Task.id, Task.parent_task_id).where(
            Task.parent_task_id.isnot(None), Task.is_deleted == False,
        ).order_by(Task.sort_order, Task.created_at, Task.id))
        for task_id, parent_id in rows:
            siblings.setdefault(parent_id, []).append(task_id)
        for task_ids in siblings.values():
            base = (Decimal(1) / len(task_ids)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            for index, task_id in enumerate(task_ids):
                weight = base if index < len(task_ids) - 1 else Decimal(1) - base * (len(task_ids) - 1)
                connection.execute(sa.update(Task).where(Task.id == task_id).values(weight=weight))
    if connection.dialect.name == "postgresql":
        op.execute(text("ALTER TYPE taskeventtype ADD VALUE IF NOT EXISTS 'REOPEN'"))
    for index in TaskEvent.__table__.indexes:
        if index.name == "ix_task_events_latest_progress":
            index.create(connection, checkfirst=True)


def downgrade():
    raise RuntimeError("Baseline adoption cannot be downgraded without data loss. Restore a verified backup instead.")
