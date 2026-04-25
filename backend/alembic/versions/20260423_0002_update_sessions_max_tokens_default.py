from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260423_0002"
down_revision = "20260420_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sessions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("sessions")}
    if "max_tokens" not in columns:
        return
    op.alter_column("sessions", "max_tokens", server_default=sa.text("10000"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sessions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("sessions")}
    if "max_tokens" not in columns:
        return
    op.alter_column("sessions", "max_tokens", server_default=sa.text("4096"))
