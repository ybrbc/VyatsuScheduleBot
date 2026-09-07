"""Add daily_send_tomorrow to users and create daily_notification_logs table."""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "20260902_01"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- users.daily_send_tomorrow ---
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "daily_send_tomorrow" not in user_cols:
        op.add_column(
            "users",
            sa.Column(
                "daily_send_tomorrow",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    # --- daily_notification_logs ---
    if "daily_notification_logs" not in existing_tables:
        op.create_table(
            "daily_notification_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("target_date", sa.Date(), nullable=False),
            sa.Column("notification_date", sa.Date(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=False),
            sa.Column("last_resent_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "target_date", "notification_date",
                name="uq_daily_log",
            ),
        )


def downgrade() -> None:
    op.drop_table("daily_notification_logs")
    op.drop_column("users", "daily_send_tomorrow")
