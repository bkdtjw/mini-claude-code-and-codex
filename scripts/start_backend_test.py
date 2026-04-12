#!/bin/bash
# 启动 Agent Studio 后端并测试 X 平台

echo "=== 启动 Agent Studio 后端测试 X 平台 ==="
echo ""

cd /agent-studio/agent-studio

echo "检查代理状态..."
ps aux | grep mihomo | grep -v grep

echo ""
echo "启动后端服务..."
timeout 60 python3 -m backend.main &
BACKEND_PID=$!

echo "后端 PID: $BACKEND_PID"
echo "等待服务启动..."
sleep 10

echo ""
echo "检查服务是否启动..."
if ps -p $BACKEND_PID > /dev/null; then
    echo "✅ 后端服务正在运行"
    echo ""
    echo "可以通过以下方式测试 X 平台功能:"
    echo "1. 启动前端访问 Web UI"
    echo "2. 使用 API 调用"
    echo "3. 在完整环境中测试搜索功能"

    # 清理
    echo ""
    read -p "按回车键停止服务..."
    kill $BACKEND_PID 2>/dev/null
else
    echo "❌ 后端启动失败"
fi
