from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260531_0005"
down_revision = "20260428_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "knowledge_bases" not in tables:
        op.create_table(
            "knowledge_bases",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_knowledge_bases_name", "knowledge_bases", ["name"])
    if "kb_documents" not in tables:
        op.create_table(
            "kb_documents",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("kb_id", sa.String(length=64), nullable=False),
            sa.Column("filename", sa.Text(), nullable=False),
            sa.Column("file_type", sa.String(length=20), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_kb_documents_kb_id", "kb_documents", ["kb_id"])
    if "kb_chunks" not in tables:
        op.create_table(
            "kb_chunks",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("kb_id", sa.String(length=64), nullable=False),
            sa.Column("doc_id", sa.String(length=64), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("embedding_json", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False, server_default=""),
            sa.Column("page_num", sa.Integer(), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["doc_id"], ["kb_documents.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_kb_chunks_doc_id", "kb_chunks", ["doc_id"])
        op.create_index("ix_kb_chunks_kb_id", "kb_chunks", ["kb_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in ("kb_chunks", "kb_documents", "knowledge_bases"):
        if table in tables:
            op.drop_table(table)
