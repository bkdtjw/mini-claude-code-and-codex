from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

from backend.common.errors import AgentError
from backend.storage import database


class FakeAsyncEngine:
    def __init__(self, database_url: str) -> None:
        self.url = make_url(database_url)
        self.sync_engine = object()


def test_build_session_factory_sqlite_memory() -> None:
    engine, _ = database.build_session_factory("sqlite+aiosqlite:///:memory:")
    try:
        assert isinstance(engine.sync_engine.pool, StaticPool)
    finally:
        asyncio.run(engine.dispose())


def test_build_session_factory_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "agent_studio.db"
    engine, _ = database.build_session_factory(f"sqlite+aiosqlite:///{db_path}")
    try:
        assert db_path.parent.exists()
    finally:
        asyncio.run(engine.dispose())


def test_build_session_factory_postgresql(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    fake_engine = FakeAsyncEngine("postgresql+asyncpg://agent:password@localhost:5432/agent_studio")
    factory = object()
    monkeypatch.setattr(database.settings, "database_pool_size", 7)
    monkeypatch.setattr(database.settings, "database_max_overflow", 9)
    monkeypatch.setattr(database.settings, "database_pool_timeout", 11)
    monkeypatch.setattr(database.settings, "database_pool_recycle", 13)

    def fake_create_async_engine(database_url: str, **kwargs: object) -> FakeAsyncEngine:
        captured["database_url"] = database_url
        captured["engine_kwargs"] = kwargs
        return fake_engine

    def fake_async_sessionmaker(engine: object, *, expire_on_commit: bool) -> object:
        captured["factory_engine"] = engine
        captured["expire_on_commit"] = expire_on_commit
        return factory

    monkeypatch.setattr(database, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(database, "async_sessionmaker", fake_async_sessionmaker)

    engine, session_factory = database.build_session_factory(
        "postgresql+asyncpg://agent:password@localhost:5432/agent_studio"
    )

    assert engine is fake_engine
    assert session_factory is factory
    assert captured["database_url"] == "postgresql+asyncpg://agent:password@localhost:5432/agent_studio"
    assert captured["factory_engine"] is fake_engine
    assert captured["expire_on_commit"] is False
    assert captured["engine_kwargs"] == {
        "pool_size": 7,
        "max_overflow": 9,
        "pool_timeout": 11,
        "pool_recycle": 13,
        "pool_pre_ping": True,
    }


def test_build_session_factory_unsupported() -> None:
    with pytest.raises(AgentError, match="DB_UNSUPPORTED_BACKEND"):
        database.build_session_factory("mysql+aiomysql://agent:password@localhost:3306/agent_studio")


def test_sqlite_pragma_not_registered_for_pg(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    fake_engine = FakeAsyncEngine("postgresql+asyncpg://agent:password@localhost:5432/agent_studio")
    monkeypatch.setattr(database, "create_async_engine", lambda *_args, **_kwargs: fake_engine)
    monkeypatch.setattr(database, "async_sessionmaker", lambda *_args, **_kwargs: object())

    def fake_register_sqlite_pragma(_engine: object) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(database, "_register_sqlite_pragma", fake_register_sqlite_pragma)

    database.build_session_factory("postgresql+asyncpg://agent:password@localhost:5432/agent_studio")

    assert calls == 0
