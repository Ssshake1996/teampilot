"""Add responsibility, persistent issues and management audit records."""
from alembic import op
import sqlalchemy as sa

revision = "20261104_03"
down_revision = "20261005_02"
branch_labels = None
depends_on = None


def upgrade():
    metadata = sa.MetaData()
    sa.Table("tasks", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    sa.Table("users", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    tables = [sa.Table(
        "task_governance", metadata,
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("acceptance_criteria", sa.Text(), nullable=False),
        sa.Column("deliverable_url", sa.Text()), sa.Column("deliverable_note", sa.Text()),
        sa.Column("review_status", sa.String(32), nullable=False), sa.Column("review_note", sa.Text()),
        sa.Column("handover_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ), sa.Table(
        "task_issues", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, index=True), sa.Column("resolution", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ), sa.Table(
        "task_changes", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False, index=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=False), sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )]
    for table in tables:
        table.create(op.get_bind(), checkfirst=True)


def downgrade():
    for table in ("task_changes", "task_issues", "task_governance"):
        op.drop_table(table)
