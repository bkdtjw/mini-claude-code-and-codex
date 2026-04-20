# 部署指南

## 前置条件
- Docker
- Docker Compose v2
- PostgreSQL（宿主机或远程）
- Redis（宿主机或远程）

## 环境配置
- 复制 `.env.example` 为 `.env`
- 必填项：`DATABASE_URL`、`REDIS_URL`、`AUTH_SECRET`
- 可选项：`GUNICORN_WORKERS`、`LOG_LEVEL`、`LOG_FORMAT`、`API_PORT`

## Volume 映射
docker-compose.yml 配置了以下 volume 映射：

| 宿主机路径 | 容器内路径 | 说明 |
|-----------|-----------|------|
| `./data/logs` | `/app/data/logs` | 应用日志文件 |
| `./reports` | `/app/reports` | 定时任务执行报告（持久化） |
| `./twitter_cookies.json` | `/app/twitter_cookies.json` | X/Twitter 认证 cookies（可选） |

启动前确保宿主机目录存在：
```bash
mkdir -p data/logs reports
```

> **注意**：entrypoint 脚本会在容器启动时自动修复 volume 挂载目录的权限，无需手动 chown。

### Twitter/X 搜索配置（可选）
如需使用 X 搜索功能，需要：
1. 在 `.env` 中配置 `TWITTER_USERNAME`/`TWITTER_EMAIL`/`TWITTER_PASSWORD`
2. 在项目根目录放置 `twitter_cookies.json` 文件
3. 配置 `TWITTER_PROXY_URL`（国内必需）

注意：如果未配置 Twitter 搜索，可以将 `docker-compose.yml` 中的 cookies 挂载注释掉。

## 启动
```bash
docker compose up -d --build
```

## 验证
```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
docker compose ps
```

### 容器内权限验证
```bash
# 验证 appuser 可写目录
docker compose exec app touch /app/reports/test && docker compose exec app rm /app/reports/test
docker compose exec app touch /app/data/logs/test && docker compose exec app rm /app/data/logs/test

# 验证 cookies 文件挂载（如果配置了 Twitter 搜索）
docker compose exec app ls -la /app/twitter_cookies.json
```

## 运维
- 查看日志：`docker compose logs -f app`
- 重启服务：`docker compose restart app`
- 更新代码：`git pull && docker compose up -d --build`
- 回滚到 systemd：`scripts/rollback-to-systemd.sh`

## 架构
- Gunicorn master + N 个 `UvicornWorker`
- WebSocket 通过 Redis pub/sub 跨 Worker 广播，channel 使用 `ws:session:{session_id}`
- 任务队列通过 Redis List 跨 Worker 分发，任务 key 使用 `task:{namespace}:{task_id}`
- 运行时结构化日志统一输出 JSON，包含 `trace_id`、`session_id`、`worker_id`

## Skills 目录
- 默认从仓库根目录的 `skills/` 加载所有可用 spec
- 每个 skill 目录至少包含 `SKILL.md`
- 可选文件：`prompt.md`、`tools.yaml`、`sub_agents.yaml`

示例结构：
```text
skills/
  daily-ai-news/
    SKILL.md
    prompt.md
    tools.yaml
  code-reviewer/
    SKILL.md
    prompt.md
```

## 飞书斜杠命令
- 普通消息：走主 agent，对话可持续，并可通过 `query_specs` 发现可用场景
- 斜杠命令：`/spec_id 后续文本`
- 示例：`/daily-ai-news`
- 示例：`/code-reviewer 审查 backend/core/s05_skills/runtime.py`

## CLI Run
- 交互模式保持不变：`miniclaude -w /path/to/workspace`
- 一次性执行 spec：`miniclaude run daily-ai-news`
- 带输入：`miniclaude run code-reviewer -i "审查 backend/core/"`
- 指定工作目录：`miniclaude run tech-research -w /path/to/workspace`

## 定时任务 spec_id
- `scheduled_tasks.spec_id` 为空时，仍按 `prompt` 驱动执行
- `scheduled_tasks.spec_id` 非空时，任务会按对应 spec 的 system prompt、工具白名单和模型/provider 配置执行
