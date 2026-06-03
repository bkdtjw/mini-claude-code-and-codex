from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.api.routes.knowledge import (
    create_knowledge_base,
    get_knowledge_status,
    list_knowledge_bases,
    list_knowledge_documents,
    rename_knowledge_base,
)
from backend.api.routes.knowledge_api_models import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseRenameRequest,
)
from backend.core.s13_knowledge import KnowledgeService

pytestmark = pytest.mark.asyncio


async def test_list_knowledge_bases_route(db_session_factory) -> None:
    service = KnowledgeService.from_session_factory(db_session_factory)
    kb = await service.create_kb("数字信号处理")

    response = await list_knowledge_bases()

    assert response.bases[0].id == kb.id
    assert response.bases[0].name == "数字信号处理"
    assert response.bases[0].document_count == 0


async def test_create_rename_and_list_documents_route(db_session_factory) -> None:
    created = await create_knowledge_base(KnowledgeBaseCreateRequest(name="项目文档"))
    renamed = await rename_knowledge_base(
        created.id,
        KnowledgeBaseRenameRequest(name="项目文档新版"),
    )
    docs = await list_knowledge_documents(created.id)

    assert renamed.name == "项目文档新版"
    assert docs.documents == []


async def test_knowledge_status_route_reports_queue_state() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(task_queue=object())))

    status = await get_knowledge_status(request)  # type: ignore[arg-type]

    assert status.queue_ready is True
    assert status.knowledge_ready is True
