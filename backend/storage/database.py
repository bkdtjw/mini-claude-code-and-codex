from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.common.errors import AgentError
from backend.config.settings import settings
from backend.storage.models import Base

SessionFactory = async_sessionmaker[AsyncSession]


def build_session_factory(database_url: str) -> tuple[AsyncEngine, SessionFactory]:
    url = make_url(database_url)
    if url.get_backend_name().startswith("sqlite") and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine_kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url:
        engine_kwargs["poolclass"] = StaticPool
    engine = create_async_engine(database_url, **engine_kwargs)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
            return

    return engine, async_sessionmaker(engine, expire_on_commit=False)


engine, session_factory = build_session_factory(settings.database_url)


def _ensure_message_columns(connection: object) -> None:
    inspector = inspect(connection)
    if "messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "provider_metadata_json" not in columns:
        connection.execute(text("ALTER TABLE messages ADD COLUMN provider_metadata_json TEXT"))


async def init_db(target_engine: AsyncEngine | None = None) -> None:
    try:
        async with (target_engine or engine).begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
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


__all__ = ["SessionFactory", "build_session_factory", "engine", "get_db_session", "init_db", "session_factory"]
