from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.api.routes.websocket_knowledge import prepare_knowledge_run
from backend.api.routes.websocket_support import LoopSettings, RunLoopInput, run_loop
from backend.common.types import AgentConfig, LLMRequest, LLMResponse, StreamChunk
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s13_knowledge import KnowledgeBase, SearchHit

pytestmark = pytest.mark.asyncio


class FakeKnowledgeService:
    async def get_kb(self, kb_id: str) -> KnowledgeBase | None:
        return KnowledgeBase(id=kb_id, name="数字信号处理")

    async def get_or_create_default_kb(self) -> KnowledgeBase:
        return KnowledgeBase(id="default", name="默认库")

    async def search(self, _request: object) -> list[SearchHit]:
        return [
            SearchHit(
                content="FIR 滤波器的冲激响应长度有限。",
                score=0.9,
                document_name="第7章 数字滤波器.pdf",
            )
        ]


class EmptyKnowledgeService(FakeKnowledgeService):
    async def search(self, _request: object) -> list[SearchHit]:
        return []


class EchoAdapter(LLMAdapter):
    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=request.messages[-1].content)

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


async def test_prepare_knowledge_run_builds_augmented_message() -> None:
    context = await prepare_knowledge_run(
        LoopSettings(model="mock", mode="knowledge", knowledge_base_id="kb-1"),
        "FIR 滤波器是什么",
        service=FakeKnowledgeService(),  # type: ignore[arg-type]
    )

    assert context.display_message == "FIR 滤波器是什么"
    assert "当前知识库：数字信号处理" in context.message
    assert "第7章 数字滤波器.pdf" in context.message


async def test_prepare_knowledge_run_empty_reply_keeps_kb_state() -> None:
    context = await prepare_knowledge_run(
        LoopSettings(model="mock", mode="knowledge", knowledge_base_id="kb-1"),
        "没有资料的问题",
        service=EmptyKnowledgeService(),  # type: ignore[arg-type]
    )

    assert context.empty_reply
    assert "当前知识库：数字信号处理" in context.empty_reply


async def test_run_loop_restores_display_message_after_augmented_prompt() -> None:
    sent: list[dict[str, object]] = []

    async def send_message(message: dict[str, object]) -> None:
        sent.append(message)

    loop = AgentLoop(
        config=AgentConfig(model="mock-model"),
        adapter=EchoAdapter(),
        tool_registry=ToolRegistry(),
    )

    await run_loop(
        RunLoopInput(
            loop=loop,
            message="augmented prompt",
            display_message="original question",
            send_message=send_message,
            session_id="session-1",
        )
    )

    user_messages = [message for message in loop.messages if message.role == "user"]
    assert user_messages[0].content == "original question"
    assert sent[-1]["type"] == "done"
