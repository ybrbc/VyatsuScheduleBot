"""Add user_subject_filters table.

Allows users to mark specific subjects as always-visible or always-hidden
regardless of subgroup or display_mode settings.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "20260901_01"
down_revision = "20260829_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "user_subject_filters" not in existing_tables:
        op.create_table(
            "user_subject_filters",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("lesson_type", sa.String(length=50), nullable=True),
            sa.Column("filter_type", sa.String(length=20), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "title", "lesson_type", name="uq_usr_sbj_filter"
            ),
        )


def downgrade() -> None:
    op.drop_table("user_subject_filters")
