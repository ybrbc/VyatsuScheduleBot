"""Upgrade an existing VyatsuScheduleBot V1 database to V2.

The checks make this revision compatible with a new database where
``Base.metadata.create_all`` has already created the V2 columns.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260829_01"
down_revision = None
branch_labels = None
depends_on = None


def _columns(table_name: str) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    groups_columns = _columns("groups")
    if "last_check_at" not in groups_columns:
        op.add_column("groups", sa.Column("last_check_at", sa.DateTime(), nullable=True))

    users_columns = _columns("users")
    if "last_daily_sent" not in users_columns:
        op.add_column("users", sa.Column("last_daily_sent", sa.Date(), nullable=True))

    if "diff_display_mode" not in users_columns:
        op.add_column(
            "users",
            sa.Column(
                "diff_display_mode",
                sa.String(length=30),
                nullable=False,
                server_default=sa.text("'hide'"),
            ),
        )

    # Existing installations may have received this column manually. Preserve
    # their settings, but make rows with no setting behave like new V2 users.
    op.execute(sa.text("UPDATE users SET diff_display_mode = 'hide' WHERE diff_display_mode IS NULL"))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        display_mode = _columns("users")["display_mode"]
        if getattr(display_mode["type"], "length", None) != 30:
            op.alter_column(
                "users",
                "display_mode",
                existing_type=sa.String(length=getattr(display_mode["type"], "length", None)),
                type_=sa.String(length=30),
                existing_nullable=False,
            )
        op.alter_column(
            "users",
            "diff_display_mode",
            existing_type=sa.String(length=30),
            nullable=False,
            server_default="hide",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "users",
            "display_mode",
            existing_type=sa.String(length=30),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
    op.drop_column("users", "diff_display_mode")
    op.drop_column("users", "last_daily_sent")
    op.drop_column("groups", "last_check_at")
