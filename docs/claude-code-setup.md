# Claude Code 配置指南

## 安装 / 升级

```bash
npm install -g @anthropic-ai/claude-code@latest
claude --version   # => 2.1.112
```

## 切换提供商

用 `--settings` 加载不同配置文件，一个命令搞定：

```bash
# 智谱 glm-5.1（默认，不传 --settings 就用这个）
claude

# Kimi
claude --settings ~/.claude/settings-kimi.json

# Anthropic 官方（OAuth 网页登录）
claude --settings /dev/null
# 首次需先登录: claude auth login
```

### 配置文件说明

| 文件 | 提供商 | 用法 |
|------|--------|------|
| `~/.claude/settings.json` | 智谱 glm-5.1 | `claude`（默认） |
| `~/.claude/settings-zhipu.json` | 智谱 glm-5.1 | `--settings settings-zhipu.json` |
| `~/.claude/settings-kimi.json` | Kimi | `--settings settings-kimi.json` |
| `claude auth login` | Anthropic 官方 | `claude --settings /dev/null` |

### 查看当前认证状态

```bash
claude auth status
```

## settings.json 字段说明

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "API Key",
    "ANTHROPIC_BASE_URL": "API 代理地址",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.1",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.1",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "glm-5.1"
  },
  "model": "opus[1m]",
  "fastMode": true
}
```

| 字段 | 说明 |
|------|------|
| `ANTHROPIC_AUTH_TOKEN` | API Key |
| `ANTHROPIC_BASE_URL` | 接口地址，设了就走第三方，不设就走官方 OAuth |
| `API_TIMEOUT_MS` | 超时 3M |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 关闭遥测 |
| `ANTHROPIC_DEFAULT_*_MODEL` | 把 haiku/sonnet/opus 映射到指定模型 |
| `model` | 默认模型 |
| `fastMode` | 快速输出 |

## 本机环境

- **服务器**: 39.106.21.49
- **Claude Code**: v2.1.112
- **默认提供商**: 智谱 BigModel (glm-5.1)
