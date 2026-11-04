"""Team planning and immutable report history."""
from alembic import op
import sqlalchemy as sa

revision = "20261104_04"
down_revision = "20261104_03"
branch_labels = None
depends_on = None


def upgrade():
    metadata = sa.MetaData()
    for name in ("users", "tasks", "projects"):
        sa.Table(name, metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    def table(name, *columns, timestamps=True, constraints=()):
        base = [sa.Column("id", sa.Uuid(), primary_key=True)]
        if timestamps:
            base += [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                     sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]
        sa.Table(name, metadata, *base, *columns, *constraints).create(op.get_bind(), checkfirst=True)
    def fk(name, target):
        return sa.Column(name, sa.Uuid(), sa.ForeignKey(target + ".id"), nullable=False,
                         index=name == "project_id")
    table("week_capacities", fk("user_id", "users"), sa.Column("week_start", sa.Date(), nullable=False),
          sa.Column("available_hours", sa.Numeric(7, 1), nullable=False), sa.Column("note", sa.Text(), nullable=False),
          constraints=(sa.UniqueConstraint("user_id", "week_start"),))
    table("week_allocations", fk("task_id", "tasks"), fk("user_id", "users"), sa.Column("week_start", sa.Date(), nullable=False),
          sa.Column("hours", sa.Numeric(7, 1), nullable=False), constraints=(sa.UniqueConstraint("task_id", "user_id", "week_start"),))
    table("project_milestones", fk("project_id", "projects"), sa.Column("name", sa.String(200), nullable=False), fk("owner_id", "users"),
          sa.Column("due_date", sa.Date(), nullable=False), sa.Column("task_ids", sa.JSON(), nullable=False))
    table("task_dependencies", fk("predecessor_id", "tasks"), fk("successor_id", "tasks"),
          constraints=(sa.UniqueConstraint("predecessor_id", "successor_id"),))
    table("plan_baselines", fk("project_id", "projects"), sa.Column("label", sa.String(200), nullable=False),
          sa.Column("snapshot_json", sa.JSON(), nullable=False), fk("created_by", "users"))
    table("week_commitments", fk("project_id", "projects"), fk("task_id", "tasks"), sa.Column("week_start", sa.Date(), nullable=False),
          fk("owner_id", "users"), sa.Column("expected_outcome", sa.Text(), nullable=False), sa.Column("outcome_note", sa.Text(), nullable=False),
          constraints=(sa.UniqueConstraint("task_id", "week_start"),))
    table("retrospectives", fk("project_id", "projects"), sa.Column("week_start", sa.Date(), nullable=False),
          sa.Column("summary", sa.Text(), nullable=False), sa.Column("decisions", sa.Text(), nullable=False),
          sa.Column("action_task_ids", sa.JSON(), nullable=False), fk("created_by", "users"))
    table("report_versions", sa.Column("report_type", sa.String(16), nullable=False, index=True), sa.Column("report_json", sa.JSON(), nullable=False),
          sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
          sa.Column("audience_user_id", sa.Uuid(), sa.ForeignKey("users.id"), index=True), timestamps=False)


def downgrade():
    for name in ("report_versions", "retrospectives", "week_commitments", "plan_baselines", "task_dependencies", "project_milestones", "week_allocations", "week_capacities"):
        op.drop_table(name)
