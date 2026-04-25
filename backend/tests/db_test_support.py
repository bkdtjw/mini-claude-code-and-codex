from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.storage.database import SessionFactory, build_session_factory, init_db
from backend.storage.models import Base

_test_database_url = ""


def set_test_database_url(database_url: str) -> None:
    global _test_database_url
    _test_database_url = database_url


def get_test_database_url() -> str:
    if not _test_database_url:
        raise RuntimeError("Test database URL has not been configured.")
    return _test_database_url


async def create_test_engine_and_factory() -> tuple[AsyncEngine, SessionFactory]:
    engine, factory = build_session_factory(get_test_database_url())
    await init_db(engine)
    return engine, factory


async def truncate_database(engine: AsyncEngine) -> None:
    table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
    if not table_names:
        return
    quoted_tables = ", ".join(f'"{name}"' for name in table_names)
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE"
        )


__all__ = [
    "create_test_engine_and_factory",
    "get_test_database_url",
    "set_test_database_url",
    "truncate_database",
]
