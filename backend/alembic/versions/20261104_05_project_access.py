"""Add project visibility without changing existing company-visible projects."""
from alembic import op
import sqlalchemy as sa

revision = "20261104_05"
down_revision = "20261104_04"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if "project_access_policies" not in sa.inspect(connection).get_table_names():
        op.create_table("project_access_policies",
            sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), primary_key=True),
            sa.Column("visibility", sa.String(16), nullable=False),
            sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table("project_access_policies")
