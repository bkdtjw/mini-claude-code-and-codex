#!/bin/bash
# Agent Studio Proxy Health Check for Linux

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

echo "=== Agent Studio Proxy Health Check (Linux) ==="
echo ""

# Check 1: mihomo binary availability
print_info "Checking mihomo binary..."
if [ -f "mihomo-linux-amd64" ]; then
    print_info "✓ mihomo Linux binary exists"
    if [ -x "mihomo-linux-amd64" ]; then
        print_info "✓ mihomo Linux binary is executable"
    else
        print_warning "✗ mihomo Linux binary is not executable"
        chmod +x mihomo-linux-amd64
    fi
else
    print_warning "✗ mihomo Linux binary not found"
    print_info "Run: ./scripts/setup_linux_proxy.sh"
fi

# Check 2: Configuration files
print_info "Checking configuration files..."
if [ -f "config.yaml" ]; then
    print_info "✓ config.yaml exists"
else
    print_error "✗ config.yaml not found"
fi

if [ -f ".env" ]; then
    print_info "✓ .env file exists"
    # Check if .env has Linux paths
    if grep -q "mihomo-linux-amd64" .env; then
        print_info "✓ .env uses Linux paths"
    else
        print_warning "✗ .env may still have Windows paths"
    fi
else
    print_error "✗ .env file not found"
fi

# Check 3: Network ports
print_info "Checking network ports..."
if netstat -tlnp 2>/dev/null | grep -q ":7890"; then
    print_info "✓ Port 7890 is in use (proxy port)"
else
    print_warning "✗ Port 7890 is not in use"
fi

if netstat -tlnp 2>/dev/null | grep -q ":9090"; then
    print_info "✓ Port 9090 is in use (API port)"
else
    print_warning "✗ Port 9090 is not in use (mihomo API not running)"
fi

# Check 4: Python dependencies
print_info "Checking Python dependencies..."
if python3 -c "import httpx" 2>/dev/null; then
    print_info "✓ httpx module is available"
else
    print_error "✗ httpx module not found"
fi

if python3 -c "import yaml" 2>/dev/null; then
    print_info "✓ yaml module is available"
else
    print_error "✗ yaml module not found"
fi

# Check 5: Test API connection
print_info "Testing mihomo API connection..."
if curl -s http://127.0.0.1:9090/version > /dev/null 2>&1; then
    print_info "✓ mihomo API is accessible"
    VERSION=$(curl -s http://127.0.0.1:9090/version)
    print_info "mihomo version: $VERSION"
else
    print_warning "✗ mihomo API is not accessible"
fi

# Check 6: Backend health
print_info "Checking backend health..."
if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    print_info "✓ Backend is running"
else
    print_warning "✗ Backend is not running"
fi

echo ""
print_info "=== Proxy Health Check Complete ==="
