from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.errors import AgentError
from backend.core.task_queue_types import TaskPayload, TaskStatus
from backend.storage.database import SessionFactory, get_db_session
from backend.storage.models import SubAgentTaskRecord
from backend.storage.sub_agent_task_codec import to_record


async def save_payloads_with_capacity(
    session_factory: SessionFactory | None,
    payloads: list[TaskPayload],
    max_active: int,
) -> list[TaskPayload]:
    if not payloads:
        return []
    try:
        async with get_db_session(session_factory) as db:
            parent_task_id = _parent_id(payloads)
            await _lock_parent_capacity(db, parent_task_id)
            active_count = await _active_count(db, parent_task_id)
            if active_count + len(payloads) > max_active:
                raise AgentError(
                    "SUB_AGENT_CAPACITY_EXCEEDED",
                    f"active={active_count}, requested={len(payloads)}, max_active={max_active}",
                )
            for payload in payloads:
                db.add(to_record(payload))
            await db.commit()
            return payloads
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("SUB_AGENT_TASK_SAVE_MANY_ERROR", str(exc)) from exc


def _parent_id(payloads: list[TaskPayload]) -> str:
    ids = {payload.parent_task_id for payload in payloads}
    if len(ids) != 1:
        raise AgentError(
            "SUB_AGENT_CAPACITY_PARENT_MISMATCH",
            "capacity batch must share one parent_task_id",
        )
    return payloads[0].parent_task_id


async def _active_count(db: AsyncSession, parent_task_id: str) -> int:
    statement = (
        select(SubAgentTaskRecord.id)
        .where(
            SubAgentTaskRecord.parent_task_id == parent_task_id,
            SubAgentTaskRecord.status.in_(
                [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]
            ),
        )
        .with_for_update()
    )
    return len((await db.execute(statement)).scalars().all())


async def _lock_parent_capacity(db: AsyncSession, parent_task_id: str) -> None:
    bind = db.get_bind()
    if not parent_task_id or bind.dialect.name != "postgresql":
        return
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:parent_task_id))"),
        {"parent_task_id": parent_task_id},
    )


__all__ = ["save_payloads_with_capacity"]
