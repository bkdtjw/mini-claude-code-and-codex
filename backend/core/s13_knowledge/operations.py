from __future__ import annotations

from sqlalchemy import func, select, update

from backend.core.s13_knowledge.db_models import (
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
)
from backend.core.s13_knowledge.errors import KnowledgeError
from backend.core.s13_knowledge.models import (
    KnowledgeBase,
    KnowledgeBaseStats,
    KnowledgeDocument,
)
from backend.storage.database import SessionFactory, get_db_session


class KnowledgeOperations:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    async def move_document(
        self,
        source_kb_id: str,
        document_query: str,
        target_kb_name: str,
    ) -> tuple[KnowledgeDocument, KnowledgeBase]:
        try:
            target_name = _normalize_name(target_kb_name)
            query_key = _match_key(document_query)
            async with get_db_session(self._session_factory) as db:
                target = await _get_or_create_base(db, target_name)
                documents = (
                    await db.execute(
                        select(KnowledgeDocumentRecord).where(
                            KnowledgeDocumentRecord.kb_id == source_kb_id
                        )
                    )
                ).scalars().all()
                matches = [doc for doc in documents if query_key in _match_key(doc.filename)]
                if not matches:
                    raise KnowledgeError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "未找到要移动的文档")
                if len(matches) > 1:
                    names = "、".join(doc.filename for doc in matches[:3])
                    raise KnowledgeError("KNOWLEDGE_DOCUMENT_AMBIGUOUS", f"找到多个文档：{names}")
                document = matches[0]
                document.kb_id = target.id
                await db.execute(
                    update(KnowledgeChunkRecord)
                    .where(KnowledgeChunkRecord.doc_id == document.id)
                    .values(kb_id=target.id)
                )
                await db.commit()
                await db.refresh(document)
                await db.refresh(target)
                return KnowledgeDocument.model_validate(document.__dict__), _base(target)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_DOCUMENT_MOVE_ERROR", str(exc)) from exc

    async def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        try:
            async with get_db_session(self._session_factory) as db:
                statement = (
                    select(KnowledgeDocumentRecord)
                    .where(KnowledgeDocumentRecord.kb_id == kb_id)
                    .order_by(KnowledgeDocumentRecord.created_at.desc())
                )
                records = (await db.execute(statement)).scalars().all()
                return [KnowledgeDocument.model_validate(record.__dict__) for record in records]
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_DOCUMENT_LIST_ERROR", str(exc)) from exc

    async def list_base_stats(self) -> list[KnowledgeBaseStats]:
        try:
            async with get_db_session(self._session_factory) as db:
                statement = (
                    select(
                        KnowledgeBaseRecord,
                        func.count(KnowledgeDocumentRecord.id),
                        func.coalesce(func.sum(KnowledgeDocumentRecord.chunk_count), 0),
                        func.max(KnowledgeDocumentRecord.created_at),
                    )
                    .outerjoin(
                        KnowledgeDocumentRecord,
                        KnowledgeDocumentRecord.kb_id == KnowledgeBaseRecord.id,
                    )
                    .group_by(
                        KnowledgeBaseRecord.id,
                        KnowledgeBaseRecord.name,
                        KnowledgeBaseRecord.description,
                        KnowledgeBaseRecord.created_at,
                    )
                    .order_by(KnowledgeBaseRecord.created_at)
                )
                rows = (await db.execute(statement)).all()
                return [_stats(base, docs, chunks, latest) for base, docs, chunks, latest in rows]
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_BASE_STATS_ERROR", str(exc)) from exc


async def _get_or_create_base(db: object, name: str) -> KnowledgeBaseRecord:
    record = (
        await db.execute(select(KnowledgeBaseRecord).where(KnowledgeBaseRecord.name == name))
    ).scalar_one_or_none()
    if record is not None:
        return record
    base = KnowledgeBase(name=name)
    record = KnowledgeBaseRecord(**base.model_dump())
    db.add(record)
    await db.flush()
    return record


def _normalize_name(name: str) -> str:
    normalized = " ".join(name.strip().split())[:50]
    if not normalized:
        raise KnowledgeError("KNOWLEDGE_KB_NAME_EMPTY", "知识库名称不能为空")
    return normalized


def _match_key(value: str) -> str:
    return "".join(value.lower().strip().split())


def _base(record: KnowledgeBaseRecord) -> KnowledgeBase:
    return KnowledgeBase.model_validate(record.__dict__)


def _stats(
    record: KnowledgeBaseRecord,
    document_count: int,
    chunk_count: int,
    latest_document_at: object,
) -> KnowledgeBaseStats:
    return KnowledgeBaseStats(
        id=record.id,
        name=record.name,
        description=record.description,
        created_at=record.created_at,
        document_count=int(document_count or 0),
        chunk_count=int(chunk_count or 0),
        latest_document_at=latest_document_at if latest_document_at else None,
    )


__all__ = ["KnowledgeOperations"]
