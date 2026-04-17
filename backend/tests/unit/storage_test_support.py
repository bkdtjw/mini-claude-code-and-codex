from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.storage.database import SessionFactory, build_session_factory, init_db


async def make_test_session_factory(
    tmp_path: Path,
    name: str,
) -> tuple[AsyncEngine, SessionFactory]:
    engine, factory = build_session_factory(f"sqlite+aiosqlite:///{tmp_path / f'{name}.db'}")
    await init_db(engine)
    return engine, factory
