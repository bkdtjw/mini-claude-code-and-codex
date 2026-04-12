# Mihomo Linux 手动安装指南

由于网络问题自动下载失败，请使用以下方法手动安装 mihomo Linux 版本。

## 方法一：使用国内镜像下载

```bash
cd /agent-studio/agent-studio

# 使用 ghproxy 镜像加速下载
curl -L -o mihomo-linux-amd64.gz https://ghproxy.com/https://github.com/MetaCubeX/mihomo/releases/download/v1.19.23/mihomo-linux-amd64.gz

# 或者使用其他镜像
# curl -L -o mihomo-linux-amd64.gz https://mirror.ghproxy.com/https://github.com/MetaCubeX/mihomo/releases/download/v1.19.23/mihomo-linux-amd64.gz

# 解压
gunzip -c mihomo-linux-amd64.gz > mihomo-linux-amd64

# 添加执行权限
chmod +x mihomo-linux-amd64

# 验证
./mihomo-linux-amd64 -v
```

## 方法二：直接从项目获取

如果您有访问权限，可以：
1. 访问 https://github.com/MetaCubeX/mihomo/releases
2. 下载 `mihomo-linux-amd64.gz` 文件
3. 上传到服务器的 `/agent-studio/agent-studio/` 目录
4. 执行方法一的解压步骤

## 方法三：使用替代方案（临时）

如果暂时无法下载 mihomo，您可以：

1. **跳过代理功能**：项目的主要功能（AI 编码助手）不依赖 mihomo
   ```bash
   # 直接启动项目，不使用代理功能
   miniclaude
   ```

2. **使用系统代理**：如果已有其他代理工具
   ```bash
   # 在 .env 中设置代理
   export HTTP_PROXY=http://your-proxy:port
   export HTTPS_PROXY=http://your-proxy:port
   ```

## 验证安装

安装完成后，运行健康检查：
```bash
./scripts/check_proxy_health.sh
```

## 启动代理

如果安装成功，可以测试启动 mihomo：
```bash
# 测试配置文件
./mihomo-linux-amd64 -d . -f config.yaml -t

# 启动 mihomo（前台运行）
./mihomo-linux-amd64 -d . -f config.yaml

# 启动 mihomo（后台运行）
nohup ./mihomo-linux-amd64 -d . -f config.yaml > mihomo.log 2>&1 &
```
