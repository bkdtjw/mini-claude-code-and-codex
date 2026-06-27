# Sub2API 本机部署说明

## 访问入口

- 公网 HTTPS: https://sub2api.neuralhubs.cc
- 本机入口: http://127.0.0.1:8080
- 健康检查: https://sub2api.neuralhubs.cc/health

Sub2API 容器只绑定 `127.0.0.1:8080`，公网 HTTPS 由 Cloudflare Tunnel 转发：

```yaml
sub2api.neuralhubs.cc -> http://localhost:8080
```

## 管理员登录

- 邮箱: `admin@sub2api.local`
- 密码: 查看本目录 `.env` 里的 `ADMIN_PASSWORD`

不要把 `.env` 提交到 Git 或发给别人。

## 常用命令

在本目录执行：

```bash
docker compose ps
docker compose logs -f sub2api
docker compose restart sub2api
docker compose pull
docker compose up -d
```

## 使用流程

1. 打开 https://sub2api.neuralhubs.cc 并登录管理员账号。
2. 在后台导入上游账号 JSON，导入后检查账号状态是否可用。
3. 创建或分配用户 API Key。
4. 客户端把 base URL 指到 `https://sub2api.neuralhubs.cc`，Authorization 使用后台生成的 API Key。

常见 endpoint:

```text
Claude API: /v1/messages
OpenAI Responses API: /v1/responses
Gemini API: /v1beta/*
Antigravity Claude: /antigravity/v1/messages
Antigravity Gemini: /antigravity/v1beta/*
```

示例：

```bash
curl https://sub2api.neuralhubs.cc/v1/messages \
  -H 'Authorization: Bearer sk-xxxx' \
  -H 'Content-Type: application/json' \
  -d '{"model":"claude-3-5-sonnet-20241022","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}'
```

## 数据目录

- 应用数据: `./data`
- PostgreSQL 数据: `./postgres_data`
- Redis 数据: `./redis_data`

迁移或备份时优先整体打包 `sub2api-deploy` 目录。

## Cloudflare Tunnel

配置文件：

```text
/root/.cloudflared/config.yml
```

已备份：

```text
/root/.cloudflared/config.yml.bak-sub2api
```
