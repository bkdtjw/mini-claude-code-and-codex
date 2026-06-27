# P3 规格卡 — API 路由 /api/hooks（给 Codex）

> 上游 `docs/event-hooks-plan.md` / 规则 `AGENTS.md`。P0–P2 已合入。
> P3 把 HookStore 接成 HTTP，让前端脱离 mock 见真数据。**只做 CRUD + log + run(占位)**；真实扫描引擎是 P4。

## 本阶段 turf（破例进 api/）
- 新增 `backend/api/routes/hooks.py`、`backend/api/routes/hooks_api_models.py`
- 改 `backend/api/app.py`：① lifespan 里建单例 `app.state.hook_store = HookStore()` ② `app.include_router(hooks.router)` ③ import。**只加这三处，别动其它**。
- 新增 `backend/tests/unit/test_hooks_api.py`
- 仍**不许**碰 `frontend/`、`backend/core/s02_tools/`、event_hooks 既有逻辑（可 import）。

## 契约（与 `frontend/src/lib/hooks-api.ts` 的 wire 逐字一致）
store 的模型字段本就是 snake_case wire 格式，**直接复用**，别另造：
- 请求体（POST/PUT）= `HookDraft`（event_hooks 导出）。
- 单条响应 = `HookSummary`（含 `hook`+`state`）。
- `hooks_api_models.py` 只需三个壳：
```python
from pydantic import BaseModel
from backend.core.s07_task_system.event_hooks import HookSummary, TimelineEntry

class HookListResponse(BaseModel):
    hooks: list[HookSummary]
class HookLogResponse(BaseModel):
    entries: list[TimelineEntry]
class HookOkResponse(BaseModel):
    ok: bool
```

## 路由（hooks.py，仿 knowledge.py）
```python
router = APIRouter(prefix="/api/hooks", tags=["hooks"], dependencies=[Depends(verify_token)])

def _store(request: Request) -> HookStore:
    store = getattr(request.app.state, "hook_store", None)
    if store is None:
        raise _server_error("HOOK_STORE_UNAVAILABLE", "钩子存储未就绪", 503)
    return store
```
端点（每个 try-except，HTTPException 直抛，其余包 `_server_error`；404 用 HTTPException）：
- `GET  /api/hooks` → `HookListResponse(hooks=await store.list_summaries())`
- `POST /api/hooks` body `HookDraft` → `await store.create(draft)` → `HookSummary`
- `GET  /api/hooks/{hook_id}` → `await store.get_summary(id)`；None→404
- `PUT  /api/hooks/{hook_id}` body `HookDraft` → `await store.update(id, draft)`；None→404
- `DELETE /api/hooks/{hook_id}` → `await store.delete(id)`；True→`HookOkResponse(ok=True)`，False→404
- `POST /api/hooks/{hook_id}/run` → **P3 占位**：取 `get_summary(id)`，None→404，否则返回 `HookOkResponse(ok=True)`（真实扫描 P4 接）。注释标 `TODO(P4)`。
- `GET  /api/hooks/{hook_id}/log` → 取 `get_state(id)`；hook 不存在(`get_summary` None)→404，否则 `HookLogResponse(entries=state.timeline if state else [])`
错误 helper 同 knowledge.py 的 `_server_error(code, message, status_code=500)`。

## app.py 接线（surgical）
- import: `from backend.core.s07_task_system.event_hooks import HookStore` 和 `from backend.api.routes import hooks`（与现有 import 风格一致）。
- lifespan `_lifespan` 内、`app.state.session_store = SessionStore()` 附近加：`app.state.hook_store = HookStore()`。
- include 区（knowledge.router 旁）加：`app.include_router(hooks.router)`。

## 测试（test_hooks_api.py）
用 FastAPI 测试客户端，建最小 app：挂一个全新 `HookStore()` 到 `app.state.hook_store`、`app.dependency_overrides[verify_token] = lambda: None` 绕过鉴权、`include_router(hooks.router)`。覆盖：① POST 建钩子→200 且 hook.id 非空、state.summary=="尚未扫描" ② GET 列表含它 ③ GET 单条 ④ PUT 改 name 后 created_at 不变 ⑤ DELETE→ok，再 GET→404 ⑥ GET 不存在 id→404 ⑦ /log 返回 entries 列表 ⑧ accounts `@Polymarket` 经 POST 后被规范化成 `polymarket`。不发真实网络。

## 完工报告
新增/改动文件、各端点方法+路径、app.py 改的三处行号、`python3 -m pytest backend/tests/unit/test_hooks_api.py -q` 结果，并回归 4 个 event_hooks 套件。确认没碰 frontend / s02。
