from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import LLMRequest, LLMResponse, Message, StreamChunk
from backend.core.s06_context_compression.level3_summary import (
    SummaryArchiveRequest,
    summarize_archive,
)


class SummaryAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=(
                "<structured_summary>\n"
                "  <goal>继续完成任务</goal>\n"
                "  <constraints>无</constraints>\n"
                "  <identifiers>/tmp/a.py</identifiers>\n"
                "  <decisions>保留旧摘要</decisions>\n"
                "  <failures>无</failures>\n"
                "  <pending>继续测试</pending>\n"
                "  <narrative>这是新的摘要。</narrative>\n"
                "</structured_summary>"
            )
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        _ = request
        if False:
            yield StreamChunk(type="text", data="")


@pytest.mark.asyncio
async def test_level3_summary_appends_summary_chain(tmp_path) -> None:
    adapter = SummaryAdapter()
    old_summary = Message(
        role="user",
        kind="summary",
        content="<conversation_summary>\nold\n</conversation_summary>",
    )
    messages = [
        Message(role="system", content="stable"),
        old_summary,
        *[Message(role="user", content=f"turn {index}") for index in range(7)],
    ]

    compacted = await summarize_archive(
        SummaryArchiveRequest(
            messages=messages,
            adapter=adapter,
            model="model",
            sessions_dir=str(tmp_path),
            session_id="session-a",
        )
    )

    summaries = [message for message in compacted if message.kind == "summary"]
    assert summaries[0] is old_summary
    assert len(summaries) == 2
    assert "<structured_summary>" in summaries[1].content
    assert "<conversation_summary>" in summaries[1].content
    assert "无损备份:" in summaries[1].content
    assert adapter.requests[0].max_tokens == 5000
