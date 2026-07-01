from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.core.s07_task_system import event_hooks as eh
from backend.core.s07_task_system.event_hooks_runtime import HookRuntimeError, make_assess_fn
from backend.core.s07_task_system.event_hooks_runtime.llm import (
    ASSESS_MAX_TOKENS,
    ASSESS_RETRY_MAX_TOKENS,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None


class SequenceAdapter:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.requests: list[Any] = []

    async def complete(self, request: Any) -> SimpleNamespace:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return SimpleNamespace(content=self._responses[index])


def _hook() -> eh.EventHook:
    return eh.EventHook(
        id="hook-1",
        name="Launch Watch",
        twitter=eh.HookTwitterConfig(accounts=["newsdesk"], keywords=["launch"]),
        sources=eh.HookSources(),
        cadence_minutes=45,
        materiality=60,
        enabled=True,
        created_at="2026-06-27T00:00:00Z",
    )


def _request() -> eh.AssessRequest:
    signal = eh.HookSignal(
        source="twitter",
        lane="account",
        text="Official launch confirmed",
        author="newsdesk",
        ts="2026-06-27T00:01:00Z",
        engagement=42,
    )
    return eh.AssessRequest(hook=_hook(), signals=[signal])


async def test_assess_retries_empty_response_with_larger_budget() -> None:
    adapter = SequenceAdapter([
        "",
        (
            '{"materiality": 95, "summary": "Confirmed", "developments": '
            '[{"text": "Official launch confirmed", "ts": "2026-06-27T00:01:00Z", '
            '"source": "twitter"}], "resolved": true}'
        ),
    ])

    result = await make_assess_fn(adapter, "test-model")(_request())

    assert result.materiality == 95
    assert result.status_hint == "resolved"
    assert [item.max_tokens for item in adapter.requests] == [
        ASSESS_MAX_TOKENS,
        ASSESS_RETRY_MAX_TOKENS,
    ]


async def test_assess_raises_after_repeated_empty_response() -> None:
    adapter = SequenceAdapter(["", ""])

    with pytest.raises(HookRuntimeError, match="HOOK_RUNTIME_ASSESS_PARSE_ERROR"):
        await make_assess_fn(adapter, "test-model")(_request())

    assert [item.max_tokens for item in adapter.requests] == [
        ASSESS_MAX_TOKENS,
        ASSESS_RETRY_MAX_TOKENS,
    ]
