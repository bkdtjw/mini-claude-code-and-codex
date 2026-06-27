# P7b 规格卡 — Exa 接线 + 透传（给 Codex）

> P0–P6 上线，P7a（纯包 Exa 端口 + 首扫基线）已合入。P7b 把真实 `exa_search` 绑成 `ExaSearchFn`、塞进 `HookRuntime`、并在调度与 `/run` 透传给 `run_hook`，让 Exa 真正参与扫描。

## turf
- 新增 `backend/core/s07_task_system/event_hooks_runtime/exa.py`
- 改 `event_hooks_runtime/__init__.py`：`HookRuntime` 加 `exa_search_fn` 字段（默认 None）；`build_hook_runtime` 构造它；`__getattr__` 懒加载 `make_exa_search_fn`
- 改 `event_hooks_runtime/scheduler.py`：`scan_due_hooks` 调 `run_hook` 时透传 `exa_search_fn=runtime.exa_search_fn`
- 改 `backend/api/routes/hooks.py`：`/run` 调 `run_hook` 时透传 `exa_search_fn=runtime.exa_search_fn`
- 新增 `backend/tests/unit/test_event_hooks_runtime_exa.py`，扩 `test_hooks_api.py`/`test_event_hooks_scheduler.py` 验透传
- 纯包 `event_hooks/` 只 import，不改。

## exa.py
```python
from datetime import UTC, datetime, timedelta
from backend.core.s02_tools.builtin.exa_search import ExaResult, ExaSearchError, ExaSearchRequest, exa_search
from backend.core.s07_task_system.event_hooks import ExaQuery, ExaSearchFn
from backend.core.s07_task_system.event_hooks_runtime import HookRuntimeError

def make_exa_search_fn(api_key: str, proxy_url: str = "") -> ExaSearchFn:
    async def search(query: ExaQuery) -> list[ExaResult]:
        try:
            end = datetime.now(UTC)
            start = end - timedelta(days=query.days)
            request = ExaSearchRequest(
                query=query.query, api_key=api_key,
                start_published=start, end_published=end,
                num_results=query.num_results, proxy_url=proxy_url,
            )
            return await exa_search(request)
        except ExaSearchError:
            return []                      # 降级：exa 挂了/限频/缺key 不拖垮扫描
        except HookRuntimeError:
            raise
        except Exception as exc:
            raise HookRuntimeError(f"HOOK_RUNTIME_EXA_ERROR: {exc}") from exc
    return search
```
`ExaResult` 结构上满足纯包的 `ExaHit`（字段 title/url/published_date/author/highlights/text 一致）。

## __init__.py 改动
- `HookRuntime` 加字段：`exa_search_fn: Any = None`（保持 arbitrary_types_allowed）。
- `build_hook_runtime`：
  ```python
  exa_key = settings.exa_api_key
  exa_fn = _factory("make_exa_search_fn")(exa_key, settings.exa_proxy_url) if exa_key else None
  ```
  返回的 `HookRuntime(...)` 多带 `exa_search_fn=exa_fn`。
- `__getattr__` 增加分支：`name == "make_exa_search_fn"` → `from .exa import make_exa_search_fn`。`__all__` 加 `make_exa_search_fn`。
- 注意循环导入：沿用现有 PEP 562 懒加载方式，别在 `__init__` 顶部 import `.exa`。

## scheduler.py（一处）
`scan_due_hooks` 里的 `run_hook(...)` 调用追加 `exa_search_fn=runtime.exa_search_fn`（其余不动）。

## hooks.py /run（一处）
`run_hook(...)` 调用追加 `exa_search_fn=getattr(runtime, "exa_search_fn", None)`（其余不动）。

## 测试
- exa adapter：monkeypatch `event_hooks_runtime.exa.exa_search` → 记录入参的假函数；断言 ① ExaQuery→ExaSearchRequest 映射（query/num_results、`start_published`≈now-days、api_key/proxy_url 透传）② 返回的 ExaResult 列表原样返回 ③ `ExaSearchError` → 返回 []。
- build_hook_runtime（扩）：有 exa_key → `runtime.exa_search_fn` 非 None；空 key → None（monkeypatch settings.exa_api_key 两种情况，沿用 P5 测试里 monkeypatch runtime 模块全局的方式）。
- scheduler / hooks_api（扩或新加）：假 runtime 带一个记录调用的 `exa_search_fn`，触发 scan/`/run`，断言 run_hook 收到了它（可用一个会把 exa_search_fn 记进闭包的假 run_hook，或断言假 exa_search_fn 被调用）。
- 不发真实网络。

## 完工报告
新增/改文件、`make_exa_search_fn` 签名、`HookRuntime` 新字段、scheduler/hooks.py 改动行、`python3 -m pytest backend/tests/unit/test_event_hooks_runtime_exa.py backend/tests/unit/test_hooks_api.py backend/tests/unit/test_event_hooks_scheduler.py -q` + 回归全部 event_hooks 套件 + `python3 -c "import backend.api.app"`。不碰 frontend、纯包 event_hooks/。
