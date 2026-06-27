# P6 规格卡 — 调度集成 + /run 接真引擎（给 Codex）

> 上游 `docs/event-hooks-plan.md` / 规则 `AGENTS.md`。P0–P5 已合入。
> P6 让引擎**真跑起来**：app 内周期扫描到期钩子、`/run` 手动触发真扫描。这是最后一块集成。

## 本阶段 turf
- 新增 `backend/core/s07_task_system/event_hooks_runtime/scheduler.py`
- 新增 `backend/api/event_hooks_startup.py`（仿 `backend/api/morning_report_startup.py`）
- 改 `backend/api/app.py`：lifespan try 内启动、finally 内停（各一处，仿 morning_report 的两处）
- 改 `backend/api/routes/hooks.py`：`/run` 占位换真实现
- 新增/扩展测试
- 仍**不许**碰 `frontend/`、`event_hooks/` 纯包（import only）。`event_hooks_runtime/` 可继续 import s02/adapters/config。

## scheduler.py（放 event_hooks_runtime/，可测）
```python
import asyncio
from datetime import UTC, datetime
from backend.core.s07_task_system.event_hooks import HookStore, HookSummary, RunOutcome, adaptive_cadence, run_hook
from backend.core.s07_task_system.event_hooks_runtime import HookRuntime, HookRuntimeError

def is_due(summary: HookSummary, now_iso: str) -> bool
async def scan_due_hooks(store: HookStore, runtime: HookRuntime, *, now_fn=_utc_now) -> list[RunOutcome]

class HookScheduler:
    def __init__(self, store: HookStore, runtime: HookRuntime, *, tick_seconds: float = 60.0)
    async def start(self) -> None          # asyncio.create_task(self._loop())
    async def stop(self) -> None           # 取消任务、await 吞 CancelledError
    async def _loop(self) -> None          # while running: try scan_due_hooks except log; await sleep(tick)
```
- `is_due`：`hook.enabled is False` → False；`cadence = adaptive_cadence(state.status if state else "developing", hook.cadence_minutes)`；`cadence <= 0`(resolved) → False；`last_scanned` 空 → True；否则 `分钟差(now - last_scanned) >= cadence`。本地 `_minutes_since(last_iso, now_iso)`，解析失败→视为 due(返回大数)。
- `scan_due_hooks`：遍历 `store.list_summaries()`，对 `is_due` 的逐个 `await run_hook(summary.hook, store, twitter_search_fn=runtime.twitter_search_fn, assess_fn=runtime.assess_fn, push_fn=runtime.push_fn)`；**每个钩子 try-except 隔离**（一个失败不影响其它、不停循环），收集 outcomes 返回。
- 全 async try-except → `HookRuntimeError`（loop 内部吞掉单轮异常、继续）。

## event_hooks_startup.py（放 backend/api/，仿 morning_report_startup）
```python
_active: HookScheduler | None = None

async def start_event_hooks_engine(app, provider_manager) -> HookScheduler | None:
    # 整个函数 try-except：失败只 log，不抛（绝不能拖垮 app 启动）
    # 1. providers = await provider_manager.list_all(); 无 → log 返回 None
    #    default = next((p for p in providers if p.is_default), providers[0])
    #    adapter = await provider_manager.get_adapter(default.id)
    # 2. runtime = build_hook_runtime(adapter, settings.default_model)
    # 3. app.state.hook_runtime = runtime
    # 4. scheduler = HookScheduler(app.state.hook_store, runtime); await scheduler.start()
    # 5. global _active = scheduler; 返回 scheduler

async def stop_event_hooks_engine() -> None  # 停 _active（仿 stop_morning_report_cron）
```

## app.py（2 处，surgical）
- lifespan try 内、`start_morning_report_cron(...)` 那段**之后**（同一 try 层级）加：
```python
            try:
                from backend.api.event_hooks_startup import start_event_hooks_engine
                await start_event_hooks_engine(app, provider_manager)
            except Exception:  # noqa: BLE001
                logger.exception("event_hooks_engine_start_failed")
```
- finally 内、`stop_morning_report_cron()` 那段旁加对称的 stop（try 包裹）。
> 别动其它行。`provider_manager` 已在 lifespan 顶部 import（`from backend.api.routes.providers import provider_manager`）。

## hooks.py /run（换真实现）
```python
from backend.core.s07_task_system.event_hooks import run_hook  # 顶部加

@router.post("/{hook_id}/run", response_model=HookOkResponse)
async def run_hook_now(request: Request, hook_id: str) -> HookOkResponse:
    try:
        store = _store(request)
        summary = await store.get_summary(hook_id)
        if summary is None:
            raise _not_found()
        runtime = getattr(request.app.state, "hook_runtime", None)
        if runtime is None:
            raise _server_error("HOOK_RUNTIME_UNAVAILABLE", "扫描引擎未就绪", 503)
        await run_hook(summary.hook, store, twitter_search_fn=runtime.twitter_search_fn,
                       assess_fn=runtime.assess_fn, push_fn=runtime.push_fn)
        return HookOkResponse(ok=True)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _server_error("HOOK_RUN_ERROR", str(exc)) from exc
```

## 测试
- `test_event_hooks_scheduler.py`：is_due 各分支（未扫过→True、刚扫过→False、resolved→False、disabled→False、过期→True）；scan_due_hooks 用**真 HookStore + 假 runtime fn**（twitter_search_fn 返回假 TweetLike、assess_fn 返回 Assessment、push_fn 记调用），断言只有到期钩子被扫、某钩子抛错不影响其它、返回 outcomes。
- 扩 `test_hooks_api.py`：给 `app.state.hook_runtime` 挂一个假 runtime（三个 async fn），POST `/run` → 200，且 run 被触发；无 runtime → 503。
- 不发真实网络 / LLM。

## 完工报告
新增/改动文件、`is_due`/`scan_due_hooks`/`HookScheduler`/`start_event_hooks_engine` 签名、app.py 两处行号、`python3 -m pytest backend/tests/unit/test_event_hooks_scheduler.py backend/tests/unit/test_hooks_api.py -q` + 回归全部 event_hooks 套件、`python3 -c "import backend.api.app"`。
