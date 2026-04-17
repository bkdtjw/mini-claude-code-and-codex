from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from backend.common.errors import AgentError
from backend.config.settings import settings
from backend.storage.models import Base

SessionFactory = async_sessionmaker[AsyncSession]


def build_session_factory(database_url: str) -> tuple[AsyncEngine, SessionFactory]:
    url = make_url(database_url)
    backend_name = url.get_backend_name()
    if backend_name.startswith("sqlite"):
        _ensure_sqlite_directory(url)
        engine = create_async_engine(database_url, **_build_sqlite_engine_kwargs(database_url))
        _register_sqlite_pragma(engine)
    elif backend_name.startswith("postgresql"):
        engine = create_async_engine(database_url, **_build_postgres_engine_kwargs())
    else:
        raise AgentError("DB_UNSUPPORTED_BACKEND", f"Unsupported database backend: {backend_name}")
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _ensure_sqlite_directory(url: URL) -> None:
    if not url.database or url.database == ":memory:":
        return
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def _build_sqlite_engine_kwargs(database_url: str) -> dict[str, object]:
    engine_kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url:
        engine_kwargs["poolclass"] = StaticPool
    return engine_kwargs


def _build_postgres_engine_kwargs() -> dict[str, object]:
    return {
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout,
        "pool_recycle": settings.database_pool_recycle,
        "pool_pre_ping": True,
    }


def _register_sqlite_pragma(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            return


engine, session_factory = build_session_factory(settings.database_url)


def _ensure_message_columns(connection: object) -> None:
    # Legacy SQLite upgrade hook until Alembic replaces create_all-based schema sync.
    inspector = inspect(connection)
    if "messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "provider_metadata_json" not in columns:
        connection.execute(text("ALTER TABLE messages ADD COLUMN provider_metadata_json TEXT"))


async def init_db(target_engine: AsyncEngine | None = None) -> None:
    resolved_engine = target_engine or engine
    try:
        async with resolved_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if resolved_engine.url.get_backend_name().startswith("sqlite"):
                await connection.run_sync(_ensure_message_columns)
    except Exception as exc:  # noqa: BLE001
        raise AgentError("DB_INIT_ERROR", str(exc)) from exc


@asynccontextmanager
async def get_db_session(factory: SessionFactory | None = None) -> AsyncIterator[AsyncSession]:
    try:
        async with (factory or session_factory)() as session:
            yield session
    except Exception as exc:  # noqa: BLE001
        raise AgentError("DB_SESSION_ERROR", str(exc)) from exc


__all__ = [
    "SessionFactory",
    "build_session_factory",
    "engine",
    "get_db_session",
    "init_db",
    "session_factory",
]
