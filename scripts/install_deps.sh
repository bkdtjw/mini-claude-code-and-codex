#!/bin/bash
# 安装 Agent Studio 基础依赖（不含代理功能）

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Set the project directory
PROJECT_DIR="/agent-studio/agent-studio"
cd "$PROJECT_DIR" || exit 1

print_info "=== Agent Studio 基础依赖安装 ==="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 未安装"
    exit 1
fi

print_info "创建虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

print_info "激活虚拟环境..."
source venv/bin/activate

print_info "安装基础 Python 依赖..."
pip install --quiet --upgrade pip

# 核心依赖
print_info "安装核心依赖..."
pip install --quiet \
    fastapi \
    uvicorn[standard] \
    pydantic \
    pydantic-settings \
    python-multipart \
    httpx \
    sqlalchemy \
    alembic

# AI 模型适配器
print_info "安装 AI 适配器..."
pip install --quiet \
    anthropic \
    openai

# 前端依赖
if command -v npm &> /dev/null; then
    print_info "安装前端依赖..."
    if [ ! -d "frontend/node_modules" ]; then
        cd frontend
        npm install --silent
        cd ..
    fi
else
    print_warning "npm 未安装，前端将不可用"
fi

print_info ""
print_info "✅ 基础依赖安装完成！"
print_info ""
print_info "注意：代理功能需要 mihomo，由于网络问题暂时跳过"
print_info "项目的主要功能（AI 编码助手）不受影响"
print_info ""
print_info "现在可以运行: miniclaude"
