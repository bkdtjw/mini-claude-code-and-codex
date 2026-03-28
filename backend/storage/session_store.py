from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from backend.common.errors import AgentError
from backend.common.types import Message, Session
from backend.storage.database import SessionFactory, get_db_session
from backend.storage.models import MessageRecord, SessionRecord
from backend.storage.serializers import to_message, to_message_record, to_session


class SessionStore:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    async def create(self, session: Session, title: str = "", workspace: str = "") -> Session:
        try:
            async with get_db_session(self._session_factory) as db:
                db.add(
                    SessionRecord(
                        id=session.id,
                        title=title,
                        workspace=workspace,
                        model=session.config.model,
                        provider=session.config.provider,
                        system_prompt=session.config.system_prompt,
                        status=session.status,
                        max_tokens=session.config.max_tokens,
                        temperature=session.config.temperature,
                        created_at=session.created_at,
                    )
                )
                for message in session.messages:
                    db.add(to_message_record(session.id, message))
                await db.commit()
            return session
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_CREATE_ERROR", str(exc)) from exc

    async def get(self, session_id: str) -> Session | None:
        try:
            async with get_db_session(self._session_factory) as db:
                statement = select(SessionRecord).options(selectinload(SessionRecord.messages)).where(SessionRecord.id == session_id)
                record = (await db.execute(statement)).scalar_one_or_none()
                if record is None:
                    return None
                messages = [to_message(item) for item in sorted(record.messages, key=lambda current: (current.timestamp, current.id))]
                return to_session(record, messages)
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_GET_ERROR", str(exc)) from exc

    async def list_all(self) -> list[Session]:
        try:
            async with get_db_session(self._session_factory) as db:
                statement = select(SessionRecord).options(selectinload(SessionRecord.messages)).order_by(SessionRecord.created_at.desc())
                records = (await db.execute(statement)).scalars().unique().all()
                return [
                    to_session(record, [to_message(item) for item in sorted(record.messages, key=lambda current: (current.timestamp, current.id))])
                    for record in records
                ]
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_LIST_ERROR", str(exc)) from exc

    async def update_title(self, session_id: str, title: str) -> Session | None:
        try:
            async with get_db_session(self._session_factory) as db:
                await db.execute(update(SessionRecord).where(SessionRecord.id == session_id).values(title=title))
                await db.commit()
            return await self.get(session_id)
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_UPDATE_TITLE_ERROR", str(exc)) from exc

    async def update_status(self, session_id: str, status: str) -> None:
        try:
            async with get_db_session(self._session_factory) as db:
                await db.execute(update(SessionRecord).where(SessionRecord.id == session_id).values(status=status))
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_UPDATE_STATUS_ERROR", str(exc)) from exc

    async def delete(self, session_id: str) -> bool:
        try:
            async with get_db_session(self._session_factory) as db:
                result = await db.execute(delete(SessionRecord).where(SessionRecord.id == session_id))
                await db.commit()
                return bool(result.rowcount)
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_DELETE_ERROR", str(exc)) from exc

    async def save_messages(self, session_id: str, messages: list[Message]) -> None:
        try:
            async with get_db_session(self._session_factory) as db:
                if await db.get(SessionRecord, session_id) is None:
                    return
                await db.execute(delete(MessageRecord).where(MessageRecord.session_id == session_id))
                for message in messages:
                    db.add(to_message_record(session_id, message))
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_SAVE_MESSAGES_ERROR", str(exc)) from exc

    async def get_messages(self, session_id: str) -> list[Message]:
        try:
            async with get_db_session(self._session_factory) as db:
                statement = select(MessageRecord).where(MessageRecord.session_id == session_id).order_by(MessageRecord.timestamp, MessageRecord.id)
                records = (await db.execute(statement)).scalars().all()
                return [to_message(record) for record in records]
        except Exception as exc:  # noqa: BLE001
            raise AgentError("SESSION_STORE_GET_MESSAGES_ERROR", str(exc)) from exc


__all__ = ["SessionStore"]
