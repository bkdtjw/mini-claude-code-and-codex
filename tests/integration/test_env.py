from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from backend.config.settings import settings
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s13_knowledge.embedder import ZhipuEmbedder
from backend.storage.database import get_db_session

pytestmark = pytest.mark.asyncio


async def test_zhipu_embedding_dim() -> None:
    assert settings.zhipu_api_key, "ZHIPU_API_KEY must be configured for integration tests"
    embedder = ZhipuEmbedder(
        settings.zhipu_api_key,
        settings.zhipu_embedding_model,
        settings.zhipu_embedding_dimensions,
    )
    vectors = await embedder.embed(["联测环境探针"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 2048


async def test_postgres_connects() -> None:
    async with get_db_session() as db:
        version = (await db.execute(text("select version()"))).scalar_one()
    assert "PostgreSQL" in version


async def test_pgvector_extension_column_and_index_exist() -> None:
    async with get_db_session() as db:
        extension = (
            await db.execute(
                text("select extversion from pg_extension where extname = 'vector'")
            )
        ).scalar_one_or_none()
        column = (
            await db.execute(
                text(
                    "select data_type, udt_name from information_schema.columns "
                    "where table_name = 'kb_chunks' and column_name = 'embedding'"
                )
            )
        ).first()
        index = (
            await db.execute(
                text(
                    "select indexdef from pg_indexes where tablename = 'kb_chunks' "
                    "and indexdef ilike '%ivfflat%'"
                )
            )
        ).first()
    assert extension is not None, "pgvector extension is not installed"
    assert column is not None and column.udt_name == "vector"
    assert index is not None


async def test_redis_db1_connects(redis_db1: object) -> None:
    assert await redis_db1.ping() is True


async def test_tool_registry_registers_knowledge_tools() -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=os.getcwd(), mode="readonly")
    names = {definition.name for definition in registry.list_definitions()}
    assert {
        "knowledge_ingest",
        "knowledge_search",
        "knowledge_list_kbs",
        "knowledge_switch",
    }.issubset(names)
