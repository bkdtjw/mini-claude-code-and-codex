from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.common.types import ToolResult
from backend.core.s06_context_compression import LayeredCompressor, LayeredCompressorConfig


class NoopAdapter:
    async def complete(self, request: object) -> object:
        raise AssertionError("Level 1 must not call the LLM")


@pytest.mark.asyncio
async def test_process_tool_result_keeps_large_output_until_threshold(tmp_path: Path) -> None:
    output = json.dumps(
        [
            {"item_id": f"item-{index}", "name": f"商品{index}", "price": index}
            for index in range(300)
        ],
        ensure_ascii=False,
    )
    compressor = LayeredCompressor(
        NoopAdapter(),  # type: ignore[arg-type]
        "model",
        LayeredCompressorConfig(artifacts_dir=str(tmp_path), session_id="sid"),
    )

    result = await compressor.process_tool_result(ToolResult(tool_call_id="tc1", output=output))

    assert result.output == output
    assert result.artifacts == []
    assert list(tmp_path.rglob("*.json")) == []
