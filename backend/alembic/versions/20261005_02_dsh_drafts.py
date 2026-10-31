"""Add single-use DSH drafts without changing business records."""
from alembic import op
from app.models.dsh_draft import DshDraft

revision = "20261005_02"
down_revision = "20261005_01"
branch_labels = None
depends_on = None


def upgrade():
    DshDraft.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table("dsh_drafts")
