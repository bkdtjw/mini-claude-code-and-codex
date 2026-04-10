# 动态定时任务调度系统 — 实现规格文档

> 目标：构建一个通用的动态定时任务调度系统，用户可以随时创建、修改、删除定时任务。
> 系统应支持任意已注册的工具组合，不限于单一场景。
> 时区统一使用北京时间（UTC+8）。

---

## 一、系统架构概述

### 核心思路

```
用户动态配置任务
    ↓
调度引擎（北京时间 cron）
    ↓
任务执行器（调用已注册的工具链）
    ↓
结果处理（LLM 总结 / 原始输出）
    ↓
通知推送（飞书 / 其他渠道）
```

### 关键设计原则

1. **动态性**：任务可以在运行时通过 API/Tool 创建、修改、暂停、恢复、删除，无需重启
2. **通用性**：不绑定特定数据源或推送渠道，通过工具链组合实现任意流程
3. **可组合**：每个任务由「数据采集步骤」+「处理步骤」+「推送步骤」三段式组成
4. **持久化**：任务配置和执行历史持久化存储，重启后自动恢复
5. **北京时间**：所有 cron 表达式和时间显示统一使用 Asia/Shanghai（UTC+8）

---

## 二、数据模型

### 2.1 定时任务定义

```python
class ScheduledTask(BaseModel):
    """一个可动态管理的定时任务。"""

    task_id: str                          # 唯一标识，自动生成或用户指定
    name: str                             # 任务名称，用于展示
    description: str = ""                 # 任务描述

    # --- 调度配置 ---
    cron_expr: str = "0 7 * * *"          # cron 表达式（北京时间），默认每天 07:00
    timezone: str = "Asia/Shanghai"       # 固定北京时间
    enabled: bool = True                  # 是否启用

    # --- 执行流水线 ---
    steps: list[TaskStep]                 # 有序的执行步骤列表

    # --- 通知配置 ---
    notify: NotifyConfig | None = None    # 可选的通知渠道

    # --- 元数据 ---
    created_at: datetime
    updated_at: datetime
```

### 2.2 任务步骤

```python
class TaskStep(BaseModel):
    """任务中的一个执行步骤。"""

    step_id: str                          # 步骤标识
    tool_name: str                        # 要调用的工具名（必须已注册在 ToolRegistry 中）
    args: dict[str, Any]                  # 传给工具的参数
    output_var: str = ""                  # 将该步骤的输出存入变量名，供后续步骤引用
    condition: str = ""                   # 可选的执行条件表达式
```

**变量引用机制**：步骤的 `args` 中可以用 `${step_id.output}` 或 `${var_name}` 引用前序步骤的输出。

### 2.3 通知配置

```python
class NotifyConfig(BaseModel):
    """任务完成后的通知配置。"""

    channel: Literal["feishu", "webhook"]       # 通知渠道
    webhook_url: str = ""                        # webhook 地址（留空则用环境变量）
    secret: str = ""                             # 签名密钥
    title_template: str = ""                     # 通知标题模板，支持 {task_name}, {date} 等
    use_llm_summary: bool = False                # 是否用 LLM 对结果做总结后再推送
    llm_system_prompt: str = ""                  # LLM 总结用的 system prompt
```

### 2.4 执行记录

```python
class TaskExecutionRecord(BaseModel):
    """单次任务执行记录。"""

    task_id: str
    execution_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "success", "failed", "skipped"]
    steps_completed: int = 0
    steps_total: int = 0
    output: str = ""                     # 最终输出
    error: str = ""                      # 错误信息
    notify_sent: bool = False
    duration_seconds: float = 0.0
```

---

## 三、调度引擎

### 3.1 核心行为

```
启动时：
  1. 从持久化存储加载所有 enabled=True 的任务
  2. 计算每个任务的下次执行时间（北京时间）
  3. 启动后台循环，每分钟检查一次是否有到期任务

运行中：
  1. 每分钟 tick 一次
  2. 对比当前北京时间与所有任务的下次执行时间
  3. 到期的任务放入执行队列
  4. 执行队列中的任务按创建时间先后依次执行（或并发执行，可配置）
  5. 执行完成后更新执行记录，计算下次执行时间

动态管理：
  - 新增任务：立即加入调度列表，计算下次执行时间
  - 修改任务：更新配置，重新计算下次执行时间
  - 暂停任务：设 enabled=False，从调度列表移除
  - 恢复任务：设 enabled=True，重新加入调度列表
  - 删除任务：从调度列表和存储中彻底移除
  - 立即执行：不影响定时调度，额外触发一次
```

### 3.2 Cron 表达式（北京时间）

支持标准 5 位 cron 表达式：

```
┌───────── 分钟 (0-59)
│ ┌─────── 小时 (0-23)
│ │ ┌───── 日 (1-31)
│ │ │ ┌─── 月 (1-12)
│ │ │ │ ┌─ 星期 (0-6, 0=周日)
│ │ │ │ │
* * * * *
```

常用示例：
| 表达式 | 含义 |
|--------|------|
| `0 7 * * *` | 每天早上 7:00 |
| `30 9 * * 1-5` | 工作日 9:30 |
| `0 */2 * * *` | 每 2 小时 |
| `0 8,20 * * *` | 每天 8:00 和 20:00 |
| `0 7 * * 1` | 每周一 7:00 |

---

## 四、Tool 接口设计

注册一个名为 `scheduler` 的工具，通过 `action` 参数区分操作：

### 4.1 操作一览

| action | 说明 | 必需参数 |
|--------|------|----------|
| `create` | 创建新定时任务 | `name`, `steps`, 可选 `cron_expr`, `notify` |
| `update` | 修改已有任务 | `task_id`, 要修改的字段 |
| `delete` | 删除任务 | `task_id` |
| `enable` | 启用任务 | `task_id` |
| `disable` | 暂停任务 | `task_id` |
| `run_now` | 立即执行一次 | `task_id` |
| `status` | 查看单个任务状态 | `task_id` |
| `list` | 列出所有任务 | 无 |
| `history` | 查看执行历史 | `task_id`, 可选 `limit` |

### 4.2 Tool 参数 Schema

```python
ToolParameterSchema(
    properties={
        "action": {
            "type": "string",
            "enum": ["create", "update", "delete", "enable", "disable",
                     "run_now", "status", "list", "history"],
            "description": "操作类型",
        },
        "task_id": {
            "type": "string",
            "description": "任务 ID（create 时可选，其余必填）",
        },
        "name": {
            "type": "string",
            "description": "任务名称（create 时必填）",
        },
        "cron_expr": {
            "type": "string",
            "description": "cron 表达式（北京时间），默认 '0 7 * * *'",
        },
        "steps": {
            "type": "array",
            "description": "执行步骤数组，每项包含 tool_name 和 args",
        },
        "notify": {
            "type": "object",
            "description": "通知配置",
        },
        "limit": {
            "type": "integer",
            "description": "history 操作的返回条数限制",
        },
    },
    required=["action"],
)
```

---

## 五、执行流水线

### 5.1 步骤执行流程

```
for step in task.steps:
    1. 解析 args 中的变量引用 ${...}，替换为前序步骤的输出
    2. 检查 condition（如有），不满足则跳过
    3. 从 ToolRegistry 获取对应工具
    4. 调用工具的 execute(args) 方法
    5. 将 ToolResult.output 存入 output_var 变量
    6. 如果 is_error=True，根据策略决定是否终止
```

### 5.2 错误处理策略

- 默认：某步骤失败则终止整个任务，记录错误
- 可配置：`on_error: "continue"` 跳过失败步骤继续执行
- 通知：无论成功失败，如果配置了 notify 都会推送（失败时推送错误信息）

---

## 六、示例任务配置

### 示例 1：Twitter 每日简报 → 飞书

```json
{
  "name": "Twitter AI 圈每日简报",
  "cron_expr": "0 7 * * *",
  "steps": [
    {
      "step_id": "search_ai",
      "tool_name": "x_search",
      "args": {"query": "AI agent OR LLM OR GPT", "max_results": 20, "days": 1},
      "output_var": "ai_tweets"
    },
    {
      "step_id": "search_bloggers",
      "tool_name": "x_search",
      "args": {"query": "from:sama OR from:ylecun OR from:kaborator", "max_results": 15, "days": 1},
      "output_var": "blogger_tweets"
    }
  ],
  "notify": {
    "channel": "feishu",
    "title_template": "📰 Twitter AI 圈简报 — {date}",
    "use_llm_summary": true,
    "llm_system_prompt": "<<参见下方第七节的 Twitter 总结 Prompt>>"
  }
}
```

### 示例 2：YouTube 技术视频周报 → 飞书

```json
{
  "name": "YouTube AI 视频周报",
  "cron_expr": "0 9 * * 1",
  "steps": [
    {
      "step_id": "search_videos",
      "tool_name": "youtube_search",
      "args": {"query": "AI agent tutorial 2026", "max_results": 10}
    }
  ],
  "notify": {
    "channel": "feishu",
    "title_template": "🎬 YouTube AI 视频周报 — {date}",
    "use_llm_summary": true,
    "llm_system_prompt": "你是技术视频策展人，请将以下 YouTube 搜索结果整理为周报..."
  }
}
```

### 示例 3：代理节点健康检查 → 飞书告警

```json
{
  "name": "代理节点健康巡检",
  "cron_expr": "0 */4 * * *",
  "steps": [
    {
      "step_id": "check_proxy",
      "tool_name": "proxy_status",
      "args": {}
    }
  ],
  "notify": {
    "channel": "feishu",
    "title_template": "🔧 代理节点巡检 — {date} {time}",
    "use_llm_summary": false
  }
}
```

### 示例 4：多步骤组合任务 — 搜索 + 总结 + 写文件 + 推送

```json
{
  "name": "竞品情报日报",
  "cron_expr": "0 8 * * 1-5",
  "steps": [
    {
      "step_id": "search_competitor",
      "tool_name": "x_search",
      "args": {"query": "from:openai OR from:GoogleAI OR from:AnthropicAI", "max_results": 20, "days": 1},
      "output_var": "competitor_tweets"
    },
    {
      "step_id": "search_industry",
      "tool_name": "x_search",
      "args": {"query": "AI startup funding OR AI acquisition", "max_results": 15, "days": 1},
      "output_var": "industry_tweets"
    },
    {
      "step_id": "save_report",
      "tool_name": "file_write",
      "args": {
        "path": "/data/reports/competitor_{date}.md",
        "content": "${competitor_tweets}\n\n---\n\n${industry_tweets}"
      }
    }
  ],
  "notify": {
    "channel": "feishu",
    "title_template": "🏢 竞品情报日报 — {date}",
    "use_llm_summary": true,
    "llm_system_prompt": "你是竞争情报分析师，请将以下推文数据整理为竞品情报日报..."
  }
}
```

---

## 七、LLM Prompt 模板库

### 7.1 Twitter 推文总结 Prompt（通用）

以下 prompt 用于 `notify.llm_system_prompt`，当 `use_llm_summary=true` 时生效。

```text
# 角色

你是一位资深的科技行业分析师和信息整理专家。你的任务是将 Twitter/X 上的推文
原始数据整理成一份结构清晰、信息密度高、可直接阅读的每日简报。

# 核心能力

1. 信息筛选：从大量推文中识别高价值内容，过滤噪音
2. 主题聚类：将相关推文按话题自动归类
3. 趋势洞察：从碎片信息中提炼行业趋势和关键信号
4. 中文表达：用专业、简洁的中文撰写摘要，专有名词保留英文原文

# 输出格式

- 使用中文撰写，专有名词保留英文原文（如 GPT-4、LangChain、OpenAI）
- 输出纯 Markdown 格式，适合在飞书中直接渲染
- 每条摘要控制在 2-3 句话，突出核心信息
- 使用 emoji 标注分类：🔥 热门 | 🆕 新发布 | 💡 观点 | 📊 数据 | 🔧 工具 | ⚠️ 争议 | 🤝 投融资

# 输出结构

# 📰 {task_name} — {date}

## 🔍 今日概览
> 3-5 句话总结今天最值得关注的 2-3 个核心信号。

## 📋 详细摘要

### {自动分类名称}
1. **{话题}** — @{作者}
   {2-3 句摘要}
   - 🔗 原文链接
   - 📊 ❤️ {likes} | 🔁 {retweets} | 👁️ {views}

## 🎯 关键信号
- {signal_1}
- {signal_2}
- {signal_3}

## 📌 值得关注的账号动态
| 账号 | 核心动态 | 互动量 |
|------|----------|--------|
| @xxx | ... | ... |

---
⏰ {timestamp}（北京时间） | 📡 X/Twitter | 🤖 AI 自动生成

# 工作规则

1. 去重合并：相同话题的多条推文合并摘要，标注多个来源
2. 重要性排序：views > likes > retweets
3. 智能分类：AI/LLM、开源工具、Web3、创业投融资、产品发布、行业观点（无内容的分类跳过）
4. 过滤噪音：跳过纯广告、刷屏、无实质内容、与主题无关的推文
5. 保持客观：不加入个人评价，忠实原文
6. 链接保留：每条摘要保留原始链接
7. 空数据：标注"暂无数据"并建议调整搜索策略
```

### 7.2 竞品情报分析 Prompt

```text
# 角色
你是一位竞争情报分析师，擅长从公开信息中提取商业洞察。

# 任务
将以下社交媒体数据整理为结构化的竞品情报日报。

# 输出结构

# 🏢 竞品情报日报 — {date}

## 📊 核心发现
> 3 句话概括今天最重要的竞品动态

## 🔍 各公司动态

### {公司名}
- **动态摘要**：...
- **潜在影响**：...
- **我方建议**：...

## ⚡ 行业信号
- ...

## 📈 投融资动态
| 公司 | 事件 | 金额 | 意义 |
|------|------|------|------|

# 规则
1. 区分事实与推测，推测用"可能"/"据传"标注
2. 每条动态评估对我方的潜在影响
3. 按紧迫性排序：需立即关注 > 短期影响 > 长期趋势
```

### 7.3 通用数据总结 Prompt

```text
# 角色
你是一位数据分析师，擅长将原始数据整理成可读的报告。

# 任务
将以下数据整理成结构清晰的中文报告。

# 要求
1. 使用 Markdown 格式
2. 先给出 3 句话的整体概要
3. 然后按主题分类详述
4. 最后列出 3-5 条关键要点
5. 保持客观，不添加主观评价
6. 专有名词保留英文原文
```

---

## 八、Twitter 搜索语法参考

| 语法 | 说明 | 示例 |
|------|------|------|
| `from:username` | 特定用户的推文 | `from:elonmusk` |
| `to:username` | 回复特定用户的推文 | `to:openai` |
| `keyword1 OR keyword2` | 匹配任一关键词 | `AI OR LLM` |
| `keyword1 keyword2` | 同时包含 | `AI agent` |
| `"exact phrase"` | 精确匹配 | `"large language model"` |
| `-keyword` | 排除 | `AI -spam -ad` |
| `min_faves:N` | 最少 N 个赞 | `AI min_faves:100` |
| `min_retweets:N` | 最少 N 次转发 | `GPT min_retweets:50` |
| `lang:xx` | 限定语言 | `AI lang:zh` |
| `filter:links` | 只含链接 | `AI filter:links` |
| `filter:media` | 只含图片/视频 | `OpenAI filter:media` |

---

## 九、环境变量配置

```bash
# === 飞书 Webhook ===
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-token
FEISHU_WEBHOOK_SECRET=your-secret

# === Twitter 账号 ===
TWITTER_USERNAME=your_username
TWITTER_EMAIL=your_email
TWITTER_PASSWORD=your_password
TWITTER_PROXY_URL=http://127.0.0.1:7892
TWITTER_COOKIES_FILE=twitter_cookies.json

# === LLM ===
DEFAULT_PROVIDER=anthropic
DEFAULT_MODEL=claude-sonnet-4-20250514
```

---

## 十、实现注意事项

1. **文件拆分**：遵循项目规范，单文件不超过 200 行
2. **模块结构建议**：
   - `scheduler_models.py` — Pydantic 数据模型
   - `scheduler_engine.py` — 调度引擎（cron 解析、tick 循环）
   - `scheduler_executor.py` — 流水线执行器（步骤执行、变量替换）
   - `scheduler_store.py` — 任务持久化（JSON 文件或 SQLite）
   - `scheduler_tools.py` — Tool 注册（create/update/delete/run_now/...）
   - `scheduler_notify.py` — 通知推送（飞书 Webhook + LLM 总结）
3. **依赖注入**：搜索、LLM、推送功能通过回调函数注入，不硬编码
4. **时区处理**：使用 `datetime.timezone(timedelta(hours=8))` 或 `zoneinfo.ZoneInfo("Asia/Shanghai")`
5. **cron 解析**：可用标准库自行实现简单版，或引入 `croniter`（需说明理由）
6. **工具发现**：通过 `ToolRegistry.has(name)` 校验步骤中引用的工具是否存在
7. **测试**：每个公开接口至少一个测试用例，mock 外部 API
