from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260420_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scheduled_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("scheduled_tasks")}
    if "spec_id" in columns:
        return
    op.add_column(
        "scheduled_tasks",
        sa.Column("spec_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.alter_column("scheduled_tasks", "spec_id", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scheduled_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("scheduled_tasks")}
    if "spec_id" not in columns:
        return
    op.drop_column("scheduled_tasks", "spec_id")
