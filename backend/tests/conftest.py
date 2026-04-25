from __future__ import annotations

import os
from collections.abc import AsyncIterator, Generator
from pathlib import Path

os.environ.setdefault("LOG_FILE_DIR", str(Path("/tmp/agent-studio-tests-logs")))
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.postgres import PostgresContainer

import backend.api.lifespan_support as lifespan_support
import backend.config.redis_client as redis_client
import backend.storage.database as database
from backend.common.types import ToolDefinition, ToolParameterSchema, ToolResult
from backend.config.settings import settings
from backend.tests.db_test_support import set_test_database_url, truncate_database

PROXY_TEST_PATTERN = "test_proxy_"


def _build_lingxi_stub_tool(name: str, description: str) -> tuple[ToolDefinition, object]:
    definition = ToolDefinition(
        name=name,
        description=description,
        category="search",
        parameters=ToolParameterSchema(
            properties={"query": {"type": "string", "description": "Natural language query."}},
            required=["query"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(output="missing query", is_error=True)
        return ToolResult(output=f"{name} test stub: {query}")

    return definition, execute


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    skip_marker = pytest.mark.skip(reason="proxy tests disabled by user request")
    for item in items:
        if PROXY_TEST_PATTERN in item.nodeid:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def pg_container() -> Generator[PostgresContainer, None, None]:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def db_url(pg_container: PostgresContainer) -> str:
    return pg_container.get_connection_url(driver="asyncpg")


@pytest_asyncio.fixture
async def test_db_runtime(
    db_url: str,
) -> AsyncIterator[tuple[AsyncEngine, database.SessionFactory]]:
    settings.database_url = db_url
    os.environ["DATABASE_URL"] = db_url
    set_test_database_url(db_url)
    engine, session_factory = database.build_session_factory(db_url)
    database.engine = engine
    database.session_factory = session_factory
    lifespan_support.engine = engine
    await database.init_db(engine)
    await truncate_database(engine)
    yield engine, session_factory
    await truncate_database(engine)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def bind_test_database(
    test_db_runtime: tuple[AsyncEngine, database.SessionFactory],
) -> AsyncIterator[None]:
    yield


@pytest.fixture
def db_session_factory(
    test_db_runtime: tuple[AsyncEngine, database.SessionFactory],
) -> database.SessionFactory:
    _, session_factory = test_db_runtime
    return session_factory


@pytest_asyncio.fixture(autouse=True)
async def mock_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    original_redis_url = settings.redis_url
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    settings.redis_url = "redis://fake"
    monkeypatch.setattr(redis_client, "_redis_client", fake)
    monkeypatch.setattr(redis_client, "_redis_pool", None)
    monkeypatch.setattr(redis_client, "_initialized_url", settings.redis_url)
    yield fake
    settings.redis_url = original_redis_url
    await fake.aclose()


@pytest.fixture(autouse=True)
def stub_lingxi_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import backend.core.s02_tools.builtin.lingxi as lingxi
    except ImportError:
        return

    monkeypatch.setattr(
        lingxi,
        "create_lingxi_financial_search_tool",
        lambda: _build_lingxi_stub_tool(
            "lingxi_financial_search",
            "Lingxi financial search test stub.",
        ),
    )
    monkeypatch.setattr(
        lingxi,
        "create_lingxi_realtime_marketdata_tool",
        lambda: _build_lingxi_stub_tool(
            "lingxi_realtime_marketdata",
            "Lingxi realtime market data test stub.",
        ),
    )
    monkeypatch.setattr(
        lingxi,
        "create_lingxi_ranklist_tool",
        lambda: _build_lingxi_stub_tool(
            "lingxi_ranklist",
            "Lingxi ranklist test stub.",
        ),
    )
    monkeypatch.setattr(
        lingxi,
        "create_lingxi_smart_stock_selection_tool",
        lambda: _build_lingxi_stub_tool(
            "lingxi_smart_stock_selection",
            "Lingxi smart stock selection test stub.",
        ),
    )


@pytest.fixture(autouse=True)
def reset_feishu_settings() -> Generator[None, None, None]:
    original_values = {
        "feishu_webhook_url": settings.feishu_webhook_url,
        "feishu_webhook_secret": settings.feishu_webhook_secret,
        "feishu_app_id": settings.feishu_app_id,
        "feishu_app_secret": settings.feishu_app_secret,
        "feishu_chat_id": settings.feishu_chat_id,
        "feishu_verification_token": settings.feishu_verification_token,
        "feishu_encrypt_key": settings.feishu_encrypt_key,
    }
    for name in original_values:
        setattr(settings, name, "")
    yield
    for name, value in original_values.items():
        setattr(settings, name, value)
