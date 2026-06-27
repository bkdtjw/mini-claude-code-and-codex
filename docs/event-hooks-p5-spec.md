# P5 规格卡 — 真实运行时接线（给 Codex）

> 上游 `docs/event-hooks-plan.md` / 规则 `AGENTS.md`。纯引擎 P0–P4 已合入（全注入端口）。
> P5 是**指定的 impure 接缝**：把 P1/P2/P4 的注入端口接到真实推特/LLM/飞书。**本包允许 import s02_tools、backend/adapters、backend/config、backend/common**（纯包 `event_hooks/` 仍不许）。

## 落点（新 sibling 包，与纯包并列）
```
backend/core/s07_task_system/event_hooks_runtime/
  __init__.py    # HookRuntime + build_hook_runtime + 导出
  twitter.py     # make_twitter_search_fn
  llm.py         # make_assess_fn（提示词 + 解析）
  push.py        # make_push_fn（飞书卡）
backend/tests/unit/test_event_hooks_runtime.py
```
每文件 <200 行，全部 async try-except 自定义异常 `HookRuntimeError`。不碰 `frontend/`、`event_hooks/`（纯包，只 import）、`backend/api/`、`storage/`。

## twitter.py
```python
from backend.core.s02_tools.builtin.x_client import search_x_posts, XRateLimitError
from backend.core.s02_tools.builtin.x_models import XClientConfig, XPost, XSearchOptions
from backend.core.s07_task_system.event_hooks import TwitterQuery, TwitterSearchFn

def make_twitter_search_fn(x_config: XClientConfig) -> TwitterSearchFn:
    async def search(query: TwitterQuery) -> list[XPost]:
        options = XSearchOptions(max_results=query.max_results, days=query.days, search_type=query.search_type)
        try:
            return await search_x_posts(query.query, x_config, options)
        except XRateLimitError as exc:
            return list(exc.partial_posts)   # 限频→取部分，别丢
    return search
```
`XPost` 结构上满足 `TweetLike`。

## llm.py
`def make_assess_fn(adapter: LLMAdapter, model: str) -> AssessFn`，内部仿 `backend/common/feishu_card_formatter.py` 调用方式：
```python
from backend.adapters.base import LLMAdapter
from backend.common.types import LLMRequest, Message
```
- 构造提示词（中文）：给出 hook.name、旧局势摘要(prev_summary)、本轮 signals（每条 `[来源/车道] @作者 (engagement)：text` 截断 200 字、最多 20 条）。要求模型**只输出 JSON**：
  `{"materiality": <0-100 整数，这条进展有多重大/可信>, "summary": "<一句中文当前局势>", "resolved": <bool，事件是否已收尾>}`
  提示里强调：拿不准、像噪声/旧闻/重复→materiality 给低分；务必 JSON、不要多余文字。
- 调用：`LLMRequest(model=model, messages=[Message(role="user", content=prompt)], temperature=0.2, max_tokens=600)` → `await adapter.complete(req)` → `response.content`。
- 解析（健壮）：剥 ```json fence、`json.loads`；`materiality` clamp 0-100 取整；`summary` 转 str；`resolved is True` → `status_hint="resolved"` 否则 None。**解析失败兜底** `Assessment(materiality=0, summary="（LLM 解析失败）")`（安全：宁可判噪声也不乱推；数值分仍会把强信号托到 soft）。

## push.py
`def make_push_fn(*, feishu_client, chat_id, webhook_url="", webhook_secret="") -> PushFn`
- `_build_alert_card(hook, verdict) -> dict`：飞书 interactive 卡片（结构参考 `backend/core/s02_tools/builtin/feishu_cards.py` 现有卡）。含：header `🔔 {hook.name} · {status}`、一段 markdown（局势 summary、`转机分 {turning_score}/100`、置信门槛说明）、前 3 条 `new_entries`（`[来源] text`）。
- 发送优先级：① `feishu_client` 且 `chat_id` → `await feishu_client.send_message(chat_id=chat_id, content=json.dumps(card), msg_type="interactive")`；② 否则 `webhook_url` → POST（签名仿 `card_notify._generate_sign` / `try_send_card` 的 webhook 分支，`trust_env=False`）。两者皆无 → 记 warning 返回（不抛）。
- 构造 `FeishuClient` 的方式参照现有代码（grep 一个构造点）。

## __init__.py
```python
class HookRuntime(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    twitter_search_fn: Any
    assess_fn: Any
    push_fn: Any

def build_hook_runtime(adapter: LLMAdapter, model: str) -> HookRuntime
```
`build_hook_runtime` 读 `backend.config.settings`：
- `XClientConfig` **完全照** `backend/core/s02_tools/builtin/__init__.py`（约 153 行）现有构造方式取 username/email/password/proxy/cookies（别自创字段来源）。
- `FeishuClient` 仅当 `settings.feishu_app_id and settings.feishu_app_secret` 时构造，否则 None。
- 组装三个 fn 返回 `HookRuntime`。

## 测试（mock 外部）
- twitter: monkeypatch `event_hooks_runtime.twitter.search_x_posts` → 假 XPost 列表；断言 TwitterQuery→XSearchOptions 映射、XRateLimitError→partial_posts。
- llm: 假 adapter（`complete` 返回带 `.content` 的对象）：① 正常 JSON→Assessment 字段对、resolved→status_hint ② 带 ```json fence 也能解析 ③ 乱码→兜底 materiality=0。
- push: 假 feishu_client（记录 send_message 入参）：① 有 client+chat_id→调用一次、msg_type=interactive、content 含 hook 名 ② 无 client 有 webhook→走 httpx（monkeypatch）③ 都无→不抛。
- 不发真实网络 / 真实 LLM。

## 完工报告
新增文件、`make_*`/`build_hook_runtime`/`HookRuntime` 签名、`python3 -m pytest backend/tests/unit/test_event_hooks_runtime.py -q` 结果 + 回归全部 event_hooks/hooks_api 套件。确认纯包 `event_hooks/` 未被改、未碰 frontend/api。
