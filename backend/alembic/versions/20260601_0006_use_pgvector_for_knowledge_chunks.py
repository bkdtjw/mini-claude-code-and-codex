from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "20260601_0006"
down_revision = "20260531_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    if "embedding" not in columns:
        op.add_column("kb_chunks", sa.Column("embedding", Vector(2048), nullable=True))
    if "embedding_json" in columns:
        op.execute(
            "UPDATE kb_chunks SET embedding = embedding_json::vector "
            "WHERE embedding IS NULL AND embedding_json IS NOT NULL"
        )
        op.drop_column("kb_chunks", "embedding_json")
    op.alter_column("kb_chunks", "embedding", nullable=False)
    # vector ivfflat caps direct indexes at 2000 dims; keep 2048-dim vectors and index halfvec.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding "
        "ON kb_chunks USING ivfflat "
        "((embedding::halfvec(2048)) halfvec_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_embedding")
    if "embedding_json" not in columns:
        op.add_column("kb_chunks", sa.Column("embedding_json", sa.Text(), nullable=True))
    if "embedding" in columns:
        op.execute(
            "UPDATE kb_chunks SET embedding_json = embedding::text "
            "WHERE embedding_json IS NULL AND embedding IS NOT NULL"
        )
        op.drop_column("kb_chunks", "embedding")
    op.alter_column("kb_chunks", "embedding_json", nullable=False)


def _columns(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    if "kb_chunks" not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns("kb_chunks")}
