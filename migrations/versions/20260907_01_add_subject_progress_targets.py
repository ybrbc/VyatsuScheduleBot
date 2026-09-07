"""Add subject_progress_targets table."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260907_01"
down_revision = "20260903_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "subject_progress_targets" not in inspector.get_table_names():
        op.create_table(
            "subject_progress_targets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("lesson_type", sa.String(length=50), nullable=False),
            sa.Column(
                "subgroup", sa.String(length=10),
                nullable=False, server_default="",
            ),
            sa.Column("total_hours", sa.Integer(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.CheckConstraint(
                "total_hours > 0", name="ck_subject_progress_total_hours"
            ),
            sa.ForeignKeyConstraint(
                ["group_id"], ["groups.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "group_id", "title", "lesson_type", "subgroup",
                name="uq_subject_progress_target",
            ),
        )


def downgrade() -> None:
    op.drop_table("subject_progress_targets")
