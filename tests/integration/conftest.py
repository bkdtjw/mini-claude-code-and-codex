from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import backend.config.redis_client as redis_client
from backend.config.settings import settings
from backend.core.s13_knowledge.db_models import KnowledgeBaseRecord
from backend.storage.database import get_db_session, init_db

TEST_PREFIX = "__test__kb_"


@pytest.fixture
def test_kb_name() -> str:
    return f"{TEST_PREFIX}{uuid4().hex[:12]}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def real_db_ready() -> AsyncIterator[None]:
    await init_db()
    yield


@pytest_asyncio.fixture(autouse=True)
async def isolated_test_kbs(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    if "test_kb_name" not in request.fixturenames:
        yield
        return

    await _cleanup_test_kbs()
    yield
    await _cleanup_test_kbs()


@pytest_asyncio.fixture
async def redis_db1() -> AsyncIterator[Any]:
    original_url = settings.redis_url
    settings.redis_url = _redis_db_url(original_url, "1")
    await redis_client.close_redis()
    await redis_client.init_redis()
    client = redis_client.get_redis()
    assert client is not None
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await redis_client.close_redis()
        settings.redis_url = original_url


async def _cleanup_test_kbs() -> None:
    async with get_db_session() as db:
        ids = (
            await db.execute(
                select(KnowledgeBaseRecord.id).where(
                    KnowledgeBaseRecord.name.like(f"{TEST_PREFIX}%")
                )
            )
        ).scalars().all()
        if ids:
            await db.execute(delete(KnowledgeBaseRecord).where(KnowledgeBaseRecord.id.in_(ids)))
            await db.commit()


def _redis_db_url(url: str, db: str) -> str:
    base, _, tail = url.rpartition("/")
    if not base or not tail.isdigit():
        return f"{url.rstrip('/')}/{db}"
    return f"{base}/{db}"
