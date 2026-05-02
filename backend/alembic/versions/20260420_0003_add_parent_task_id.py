from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260420_0003"
down_revision = "20260423_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sub_agent_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("sub_agent_tasks")}
    if "parent_task_id" in columns:
        return
    op.add_column(
        "sub_agent_tasks",
        sa.Column("parent_task_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_sub_agent_tasks_parent_task_id",
        "sub_agent_tasks",
        ["parent_task_id"],
    )
    op.alter_column("sub_agent_tasks", "parent_task_id", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sub_agent_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("sub_agent_tasks")}
    if "parent_task_id" not in columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes("sub_agent_tasks")}
    if "ix_sub_agent_tasks_parent_task_id" in indexes:
        op.drop_index("ix_sub_agent_tasks_parent_task_id", table_name="sub_agent_tasks")
    op.drop_column("sub_agent_tasks", "parent_task_id")
