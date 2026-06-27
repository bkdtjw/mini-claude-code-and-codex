# P8 规格卡 — Postgres 持久化（给 Codex）

> P0–P7 上线。痛点：`HookStore` 是内存的，容器重建/重启即丢钩子。P8 让钩子+状态落 Postgres，重启不丢。**核心约束：纯包 `event_hooks/store.py` 不直接 import storage** —— 通过注入的 `HookPersistence` 端口；Postgres 实现放 `backend/storage/`，app 启动注入。现有 50+ 测试必须全绿（不传 persistence 时行为完全不变）。

## 落点
```
backend/storage/models.py            # 加 HookRecord(Base)（其余不动）
backend/storage/hook_config_store.py # 新增 HookConfigStore（仿 task_config_store.py）
backend/storage/__init__.py          # 导出 HookConfigStore（仿 TaskConfigStore）
backend/core/s07_task_system/event_hooks/store.py     # 加 HookPersistence 端口 + 可选 persistence 参数 + 写穿
backend/core/s07_task_system/event_hooks/__init__.py  # 导出 HookPersistence
backend/api/app.py                   # 注入：app.state.hook_store = HookStore(persistence=HookConfigStore())
backend/tests/unit/test_hook_config_store.py          # 新增（测试 DB）
backend/tests/unit/test_event_hooks_store.py          # 扩：fake persistence 验写穿/加载
```

## 1. HookRecord（storage/models.py，仿 ScheduledTaskRecord 风格）
```python
class HookRecord(Base):
    __tablename__ = "event_hooks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hook_json: Mapped[str] = mapped_column(Text, nullable=False)
    state_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO 串，按它排序=按时间
```
`init_db()` 已 `Base.metadata.create_all` → 启动自动建表，无需迁移。

## 2. HookConfigStore（storage/hook_config_store.py，仿 TaskConfigStore）
import：`from .database import SessionFactory, get_db_session`、`from .models import HookRecord`、`from backend.core.s07_task_system.event_hooks import EventHook, HookState, HookSummary`。错误包 `AgentError("HOOK_CONFIG_*", ...)`。
```python
class HookConfigStore:
    def __init__(self, session_factory: SessionFactory | None = None) -> None: ...
    async def load(self) -> list[HookSummary]
        # select(HookRecord).order_by(created_at)；每行 hook=EventHook.model_validate_json(row.hook_json)、
        # state=HookState.model_validate_json(row.state_json) if row.state_json else None → HookSummary
    async def save_hook(self, hook: EventHook) -> None
        # upsert：db.get(HookRecord, hook.id)；有则更新 hook_json，无则 add（hook_json/created_at/state_json=None）；commit
    async def save_state(self, hook_id: str, state: HookState) -> None
        # db.get(HookRecord, hook_id)；存在则 row.state_json = state.model_dump_json()；commit（不存在则忽略）
    async def delete(self, hook_id: str) -> None
        # delete(HookRecord).where(id==hook_id)；commit
```
序列化直接用 Pydantic（`model_dump_json`/`model_validate_json`），不需要单独 serializers 文件。

## 3. HookStore 改动（纯包，写穿）
新增端口（放 store.py 顶部或同包，**纯定义**）：
```python
from typing import Protocol
class HookPersistence(Protocol):
    async def load(self) -> list[HookSummary]: ...
    async def save_hook(self, hook: EventHook) -> None: ...
    async def save_state(self, hook_id: str, state: HookState) -> None: ...
    async def delete(self, hook_id: str) -> None: ...
```
`HookStore.__init__(self, path: str | None = None, persistence: HookPersistence | None = None)` —— 保留 path（默认 None→内存，现有测试不变），新增 persistence。
- `_ensure_initialized`：**若 `self._persistence`** → `for s in await persistence.load(): _hooks[s.hook.id]=s.hook; _states[s.hook.id]= s.state or _initial_state(s.hook)`；**否则**走原 JSON seed 逻辑。
- `create`：内存写入后，若 persistence → `await persistence.save_hook(hook)`、`await persistence.save_state(hook.id, state)`。
- `update`：内存更新后，若 persistence → `await persistence.save_hook(updated_hook)`。
- `delete`：若 persistence → `await persistence.delete(hook_id)`。
- `save_state` / `append_timeline`：内存更新后，若 persistence → `await persistence.save_state(hook_id, new_state)`。
所有 persistence 调用在既有 `try-except`(→HookStoreError) 内、`self._lock` 内（与 TaskStore 一致）。失败→HookStoreError（API 会 500；扫描里 scan_due_hooks 已逐钩子 try-except 隔离，DB 抖动只 log 不崩）。
`__init__.py` 导出 `HookPersistence`。

## 4. app.py（注入，1 处 + import）
- import：`from backend.storage import HookConfigStore`（与现有 storage import 风格一致）。
- lifespan 里 `app.state.hook_store = HookStore()` 改成 `app.state.hook_store = HookStore(persistence=HookConfigStore())`（init_db 在它之前已跑，表已建）。别动其它行。

## 5. 测试
- `test_hook_config_store.py`：用现有 storage 测试的测试 DB 夹具（grep 一个用真 session 的 storage 测试，照它的 fixture；**不要** override 成 None）。覆盖 load 空、save_hook 后 load 回来、save_state 后 state 回来、save_hook upsert（同 id 二次不重复）、delete。
- `test_event_hooks_store.py`（扩）：写一个内存 `FakePersistence` 实现 Protocol（dict 存 hook_json/state_json），构造 `HookStore(persistence=fake)`：① create→fake 里有该 hook+state ② 用同 fake 新建第二个 HookStore→`list_summaries` 能加载回来（重启模拟）③ delete→fake 删除 ④ append_timeline→fake 的 state 更新。原有不传 persistence 的用例保持不变、全绿。

## 完工报告
新增/改文件、`HookConfigStore` 方法签名、`HookPersistence` 端口、`HookStore.__init__` 新签名、app.py 改动行、`python3 -m pytest backend/tests/unit/test_hook_config_store.py backend/tests/unit/test_event_hooks_store.py -q` + 回归全部 event_hooks/runtime/hooks_api 套件 + `python3 -c "import backend.api.app"`。不碰 frontend、不破现有不传 persistence 的行为。
