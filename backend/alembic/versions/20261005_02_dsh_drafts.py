"""Historical draft schema, retained for existing database revision compatibility.

The integration has been removed from the application. This frozen definition
keeps upgrades independent of its retired ORM model and preserves old records.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_02"
down_revision = "20261005_01"
branch_labels = None
depends_on = None


def upgrade():
    metadata = sa.MetaData()
    # Resolve the historical foreign key without importing current application models.
    sa.Table("users", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    drafts = sa.Table(
        "dsh_drafts", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmation_hash", sa.String(64)),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True)),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    drafts.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table("dsh_drafts")
