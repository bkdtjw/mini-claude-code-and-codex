#!/bin/bash
# Setup Mihomo Proxy for Linux
# This script downloads and sets up the Linux version of Mihomo proxy

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

# Check if mihomo already exists
if [ -f "mihomo-linux-amd64" ]; then
    print_info "Mihomo Linux binary already exists"
    read -p "Do you want to re-download it? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

# Detect system architecture
ARCH=$(uname -m)
case $ARCH in
    x86_64)
        MIHOMO_ARCH="amd64"
        ;;
    aarch64|arm64)
        MIHOMO_ARCH="arm64"
        ;;
    *)
        print_error "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

print_info "System architecture: $ARCH (using mihomo $MIHOMO_ARCH)"

# Get latest version from GitHub API
print_info "Fetching latest Mihomo version..."
VERSION_INFO=$(curl -s "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest")
VERSION=$(echo "$VERSION_INFO" | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/' | sed 's/v//')

if [ -z "$VERSION" ]; then
    print_error "Failed to fetch version information"
    exit 1
fi

print_info "Latest Mihomo version: $VERSION"

# Download URL
DOWNLOAD_URL="https://github.com/MetaCubeX/mihomo/releases/download/v${VERSION}/mihomo-linux-${MIHOMO_ARCH}.gz"

print_info "Downloading Mihomo from: $DOWNLOAD_URL"

# Download the file
TEMP_FILE="/tmp/mihomo-linux-${MIHOMO_ARCH}.gz"
if ! curl -L -o "$TEMP_FILE" "$DOWNLOAD_URL"; then
    print_error "Failed to download Mihomo"
    exit 1
fi

# Extract the binary
print_info "Extracting Mihomo binary..."
if ! gunzip -c "$TEMP_FILE" > "mihomo-linux-${MIHOMO_ARCH}"; then
    print_error "Failed to extract Mihomo binary"
    rm -f "$TEMP_FILE"
    exit 1
fi

# Make it executable
chmod +x "mihomo-linux-${MIHOMO_ARCH}"

# Clean up
rm -f "$TEMP_FILE"

# Verify the binary
if [ ! -x "mihomo-linux-${MIHOMO_ARCH}" ]; then
    print_error "Downloaded binary is not executable"
    exit 1
fi

print_info "Mihomo binary successfully installed: mihomo-linux-${MIHOMO_ARCH}"
print_info ""
print_info "To use the proxy functionality, you need to update your config.yaml"
print_info "to point to the Linux binary instead of the Windows one."
print_info ""
print_info "Update the mihomo_path in your configuration to:"
print_info "  ${PROJECT_DIR}/mihomo-linux-${MIHOMO_ARCH}"
