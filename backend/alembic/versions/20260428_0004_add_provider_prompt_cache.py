from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260428_0004"
down_revision = "20260420_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "providers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("providers")}
    if "enable_prompt_cache" not in columns:
        op.add_column(
            "providers",
            sa.Column(
                "enable_prompt_cache",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.alter_column("providers", "enable_prompt_cache", server_default=None)
    if "prompt_cache_retention" not in columns:
        op.add_column(
            "providers",
            sa.Column("prompt_cache_retention", sa.String(length=20), nullable=True),
        )
    if "extra_body_json" not in columns:
        op.add_column(
            "providers",
            sa.Column("extra_body_json", sa.Text(), nullable=False, server_default="{}"),
        )
        op.alter_column("providers", "extra_body_json", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "providers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("providers")}
    for column in ("extra_body_json", "prompt_cache_retention", "enable_prompt_cache"):
        if column in columns:
            op.drop_column("providers", column)
