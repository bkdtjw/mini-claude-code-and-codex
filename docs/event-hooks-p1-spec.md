# P1 规格卡 — 推特两车道检索（给 Codex）

> 上游 `docs/event-hooks-plan.md` / 协作规则 `AGENTS.md`。P0（models+store）已合入，你在其上扩展。
> P1 只做 **推特检索 + 分源打标 + 去重**，输出 `list[HookSignal]` 喂给 P2。不做评分、状态、推送、真实联网。

## 关键架构约束（必须遵守）
- **不要**从 `backend/core/s02_tools/...` import 任何东西（跨模块 reach 内部，违反分层）。
- 检索靠**注入的端口** `TwitterSearchFn`：retriever 只认本地定义的 `TweetLike` Protocol 和 `TwitterQuery`。真实绑定 `search_x_posts`/`XClientConfig` 的适配器是 P3 的接线活，**P1 不写**。注入即复用——真实的 `XPost`（字段：author_name/author_handle/text/likes/retweets/replies/views/created_at/url）结构上满足 `TweetLike`。
- 测试用 fake search_fn 注入，不发真实推特请求。

## 落点
```
backend/core/s07_task_system/event_hooks/
  models.py     # 追加 HookSignal（其余不动），更新 __all__
  retrieval.py  # 新增（<200 行）
  __init__.py   # 追加导出 HookSignal / TweetLike / TwitterQuery / TwitterSearchFn / retrieve_twitter
backend/tests/unit/test_event_hooks_retrieval.py  # 新增
```

## 新模型（models.py 追加）
```python
class HookSignal(BaseModel):
    source: str                 # twitter | exa | zhipu | youtube
    lane: str                   # account | topic | confirm
    text: str
    url: str = ""
    author: str = ""            # handle，小写
    ts: str = ""                # 原始 created_at 串，保留来源格式
    engagement: int = 0         # likes + retweets，粗排/门槛用
    matched: list[str] = Field(default_factory=list)  # 命中的账号或关键词
```

## retrieval.py
```python
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

class TweetLike(Protocol):
    author_name: str
    author_handle: str
    text: str
    likes: int
    retweets: int
    created_at: str
    url: str

class TwitterQuery(BaseModel):
    query: str
    max_results: int = 25
    days: int = 7
    search_type: str = "Latest"

TwitterSearchFn = Callable[[TwitterQuery], Awaitable[Sequence[TweetLike]]]

class HookRetrievalError(Exception): ...
```
常量: `DEFAULT_DAYS=7`、`ACCOUNT_LANE_MAX=25`、`TOPIC_LANE_MAX=25`、`TOPIC_MIN_FAVES=30`。

公开函数:
```python
def build_account_query(accounts: list[str]) -> str   # "(from:a OR from:b)"；空→""
def build_topic_query(keywords: list[str], min_faves: int) -> str
    # '(\"Fable 5\" OR 解禁) min_faves:30'；含空格的词加引号；空→""
async def retrieve_twitter(
    hook: EventHook, search_fn: TwitterSearchFn, *, days: int = DEFAULT_DAYS,
) -> list[HookSignal]
```
`retrieve_twitter` 行为:
- **盯号车道（低门槛）**: 有 `hook.twitter.accounts` 才跑。query=`build_account_query`，`max_results=ACCOUNT_LANE_MAX`。每条 → `HookSignal(source="twitter", lane="account", matched=[post.author_handle.lower()], ...)`。
- **话题车道（高门槛）**: 有 `hook.twitter.keywords` 才跑。query=`build_topic_query(keywords, TOPIC_MIN_FAVES)`，`max_results=TOPIC_LANE_MAX`。每条 → `lane="topic", matched=[命中的 keyword 列表]`（大小写不敏感子串匹配）。
- 规范化: `engagement=likes+retweets`，`author=author_handle.lower()`，`ts=created_at`，保留 `text`/`url`。
- **跨车道去重**(红线③前置): 按推文 id 去重。**本地**实现 `_tweet_id(url)`（取 url 末段数字，不 import s02）。重复时保留 account 车道那条，合并两边 `matched`（去重）。
- **降级**: 某车道 search_fn 抛异常 → 该车道记空、**另一车道照常返回**（一个源挂不拖垮整体）；整体异常包成 `HookRetrievalError`。
- 返回顺序: account 车道在前、topic 在后；不强制时间排序（ts 是推特原格式，别瞎排）。

## 测试（test_event_hooks_retrieval.py，pytest-asyncio，fake 注入）
覆盖: ① account query 含每个 `from:`、topic query 含 `min_faves:` 且多词加引号 ② lane 标签与 matched 正确 ③ 跨车道同 id 去重且合并 matched、保留 account ④ 某车道抛异常时另一车道仍返回 ⑤ 空 accounts 不跑 account 车道、空 keywords 不跑 topic 车道 ⑥ engagement=likes+retweets。fake `TweetLike` 用简单 dataclass/对象即可。

## 完工报告
新增/改动文件、`retrieve_twitter`/`build_*` 签名、`HookSignal` 字段、`python3 -m pytest backend/tests/unit/test_event_hooks_retrieval.py -q` 结果。不碰 frontend / s02 / storage / 既有文件（models.py 仅追加 HookSignal）。
