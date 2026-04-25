from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.storage.database import SessionFactory
from backend.tests.db_test_support import create_test_engine_and_factory


async def make_test_session_factory(
    tmp_path: Path,
    name: str,
) -> tuple[AsyncEngine, SessionFactory]:
    _ = (tmp_path, name)
    engine, factory = await create_test_engine_and_factory()
    return engine, factory
