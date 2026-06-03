from __future__ import annotations

from backend.config.settings import settings
from backend.core.s13_knowledge.embedder import EmbeddingAdapter, ZhipuEmbedder
from backend.core.s13_knowledge.errors import KnowledgeError
from backend.core.s13_knowledge.ingest import KnowledgeIngestor
from backend.core.s13_knowledge.models import (
    IngestRequest,
    IngestResult,
    KnowledgeBase,
    KnowledgeBaseStats,
    KnowledgeDocument,
    SearchHit,
    SearchRequest,
)
from backend.core.s13_knowledge.operations import KnowledgeOperations
from backend.core.s13_knowledge.store import KnowledgeStore
from backend.storage.database import SessionFactory


class KnowledgeService:
    def __init__(
        self,
        store: KnowledgeStore | None = None,
        embedder: EmbeddingAdapter | None = None,
    ) -> None:
        self._store = store or KnowledgeStore()
        self._operations = KnowledgeOperations(self._store._session_factory)  # noqa: SLF001
        self._embedder = embedder or ZhipuEmbedder(
            settings.zhipu_api_key,
            settings.zhipu_embedding_model,
            settings.zhipu_embedding_dimensions,
        )

    @classmethod
    def from_session_factory(
        cls,
        session_factory: SessionFactory,
        embedder: EmbeddingAdapter | None = None,
    ) -> KnowledgeService:
        return cls(KnowledgeStore(session_factory), embedder)

    async def get_or_create_default_kb(self) -> KnowledgeBase:
        try:
            return await self._store.get_or_create_default()
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_DEFAULT_KB_ERROR", str(exc)) from exc

    async def create_kb(self, name: str) -> KnowledgeBase:
        try:
            return await self._store.create(name)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_CREATE_KB_ERROR", str(exc)) from exc

    async def rename_kb(self, kb_id: str, name: str) -> KnowledgeBase:
        try:
            return await self._store.rename(kb_id, name)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_RENAME_KB_ERROR", str(exc)) from exc

    async def move_document(
        self,
        source_kb_id: str,
        document_query: str,
        target_kb_name: str,
    ) -> tuple[KnowledgeDocument, KnowledgeBase]:
        try:
            return await self._operations.move_document(
                source_kb_id,
                document_query,
                target_kb_name,
            )
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_MOVE_DOCUMENT_ERROR", str(exc)) from exc

    async def list_kbs(self) -> list[KnowledgeBase]:
        try:
            return await self._store.list_bases()
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_LIST_KBS_ERROR", str(exc)) from exc

    async def list_kb_stats(self) -> list[KnowledgeBaseStats]:
        try:
            return await self._operations.list_base_stats()
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_LIST_KB_STATS_ERROR", str(exc)) from exc

    async def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        try:
            return await self._operations.list_documents(kb_id)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_LIST_DOCUMENTS_ERROR", str(exc)) from exc

    async def get_kb(self, kb_id: str) -> KnowledgeBase | None:
        try:
            return await self._store.get(kb_id)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_GET_KB_ERROR", str(exc)) from exc

    async def ingest_document(self, request: IngestRequest) -> IngestResult:
        try:
            return await KnowledgeIngestor(self._store, self._embedder).ingest(request)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_INGEST_ERROR", str(exc)) from exc

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        try:
            if not request.query.strip():
                return []
            vectors = await self._embedder.embed([request.query])
            if not vectors:
                return []
            return await self._store.search(request.kb_id, vectors[0], request.top_k)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("KNOWLEDGE_SEARCH_ERROR", str(exc)) from exc


__all__ = ["KnowledgeService"]
