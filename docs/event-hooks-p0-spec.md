# P0 规格卡 — Event Hooks 数据层（给 Codex）

> 上游总计划 `docs/event-hooks-plan.md`；协作规则见 `AGENTS.md` 的「Event Hooks 协作」。
> P0 只做 **模型 + 存储 + 测试**。不做 API 路由、检索、调度、推送（那是 P1+）。

## 落点（只在这里写）
```
backend/core/s07_task_system/event_hooks/
  __init__.py        # 唯一公开入口，导出下列模型 + HookStore
  models.py          # Pydantic v2 模型（<200 行）
  store.py           # HookStore（<200 行）
backend/tests/unit/test_event_hooks_store.py
```
> 如需 JSON 种子，放 `backend/config/event_hooks.json`（可不存在→空）。**不要**碰 `backend/storage/`（Postgres 持久化是后续单独 task，到时再授权）。

## 模型（snake_case，必须与 `frontend/src/types/hooks.ts` 逐字对应）
```python
HookStatus = Literal["developing", "stable", "escalating", "resolved"]

class HookTwitterConfig(BaseModel):
    accounts: list[str] = []   # 博主 handle，不含 @，存储时去掉前导 @ 并小写化
    keywords: list[str] = []

class HookSources(BaseModel):
    exa_web: bool = True
    zhipu_search: bool = True
    youtube: bool = False

class EventHook(BaseModel):
    id: str
    name: str
    twitter: HookTwitterConfig
    sources: HookSources
    cadence_minutes: int = 45     # 基础节奏，引擎按 status 自适应
    materiality: int = 60         # 0-100 推送门槛
    enabled: bool = True
    created_at: str               # ISO8601 UTC

class TimelineEntry(BaseModel):
    ts: str
    text: str
    is_new: bool = True
    source: str                   # twitter | exa | zhipu | youtube

class SourceHealth(BaseModel):
    source: str
    online: bool = False
    last_ok: str = ""

class HookState(BaseModel):
    hook_id: str
    status: HookStatus = "developing"
    summary: str = ""
    confidence: int = 0           # 0-100
    timeline: list[TimelineEntry] = []
    unseen_count: int = 0
    source_health: list[SourceHealth] = []
    last_scanned: str = ""

class HookSummary(BaseModel):
    hook: EventHook
    state: HookState | None = None

class HookDraft(BaseModel):       # 新建/编辑输入；无 id / created_at
    name: str
    twitter: HookTwitterConfig
    sources: HookSources
    cadence_minutes: int = 45
    materiality: int = 60
    enabled: bool = True
```
约束: `materiality`/`confidence` 用 `Field(ge=0, le=100)`；`cadence_minutes` 用 `Field(ge=1)`；`name` 去空白后非空（空则 ValueError）。

## HookStore（store.py）— 公开异步接口
内存 `dict[str, ...]` + `asyncio.Lock`；启动 seed-when-empty 读 `config/event_hooks.json`（仿 `s07_task_system/store.py` 的 `_ensure_initialized`）。所有 async 方法 try-except，错误抛自定义 `HookStoreError(Exception)`。

```python
async def list_summaries() -> list[HookSummary]
async def get_summary(hook_id: str) -> HookSummary | None
async def create(draft: HookDraft) -> HookSummary          # 生成 id=uuid4().hex、created_at；初始化空 state
async def update(hook_id: str, draft: HookDraft) -> HookSummary | None   # 保留 id/created_at/原 state
async def delete(hook_id: str) -> bool
async def get_state(hook_id: str) -> HookState | None
async def save_state(hook_id: str, state: HookState) -> None
async def append_timeline(hook_id: str, entries: list[TimelineEntry]) -> HookState | None  # 头插、保留最近 100 条、unseen_count += len(entries)
```
要求:
- `create`/`update` 时把 `twitter.accounts` 去 `@`、去空、小写、去重。
- `create` 时按 `sources` 里被打开的源初始化 `state.source_health`（online=False, last_ok=""），`state.summary="尚未扫描"`、`status="developing"`。
- `append_timeline` 给的条目标 `is_new=True`，并入既有 timeline（新的在前），超 100 条截断，更新 `unseen_count`、`last_scanned`（调用方传入 ts 或方法内置）。

## __init__.py 导出
上述全部模型 + `HookStore` + `HookStoreError`。模块外只能 import 这些。

## 测试（test_event_hooks_store.py，pytest-asyncio）
覆盖每个公开方法：create→list/get 往返、accounts 规范化（`@Polymarket`→`polymarket` 去重）、update 保留 created_at、delete、save_state/get_state、append_timeline 头插+截断+unseen 计数、name 空白报错。无外部 API，纯内存。

## 完工报告
列出新增文件、`HookStore` 各方法签名、`pytest backend/tests/unit/test_event_hooks_store.py` 结果。**不要**改 frontend / storage / 既有文件。
