from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.s02_tools.builtin.exa_search import (
    ExaResult,
    ExaSearchError,
    ExaSearchRequest,
    exa_search,
)
from backend.core.s07_task_system.event_hooks import ExaQuery, ExaSearchFn
from backend.core.s07_task_system.event_hooks_runtime import HookRuntimeError


def make_exa_search_fn(api_key: str, proxy_url: str = "") -> ExaSearchFn:
    async def search(query: ExaQuery) -> list[ExaResult]:
        try:
            end = datetime.now(UTC)
            start = end - timedelta(days=query.days)
            request = ExaSearchRequest(
                query=query.query,
                api_key=api_key,
                start_published=start,
                end_published=end,
                num_results=query.num_results,
                proxy_url=proxy_url,
            )
            return await exa_search(request)
        except ExaSearchError:
            return []
        except HookRuntimeError:
            raise
        except Exception as exc:
            raise HookRuntimeError(f"HOOK_RUNTIME_EXA_ERROR: {exc}") from exc

    return search


__all__ = ["make_exa_search_fn"]
