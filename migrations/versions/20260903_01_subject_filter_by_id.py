"""Rebuild user_subject_filters: replace (title, lesson_type) key with subject_id FK.

Old schema: unique on (user_id, title, lesson_type)
New schema: unique on (user_id, subject_id)  — allows per-subject-row control.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "20260903_01"
down_revision = "20260902_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = inspector.get_table_names()

    # Drop old table (data loss acceptable — app is in development)
    if "user_subject_filters" in existing:
        op.drop_table("user_subject_filters")

    op.create_table(
        "user_subject_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("filter_type", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"],    ["users.id"],    ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "subject_id", name="uq_usr_sbj_filter"),
    )


def downgrade() -> None:
    op.drop_table("user_subject_filters")
    op.create_table(
        "user_subject_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("lesson_type", sa.String(50), nullable=True),
        sa.Column("filter_type", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "title", "lesson_type",
                            name="uq_usr_sbj_filter"),
    )
