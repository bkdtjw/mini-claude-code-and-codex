#!/usr/bin/env python3
"""
测试 mihomo 代理连接
"""

import httpx
import json

def test_proxy_connection():
    """测试代理连接"""
    # httpx 使用字符串格式的代理 URL
    proxy_url = "http://127.0.0.1:7890"

    print("=== 测试 mihomo 代理连接 ===")
    print()

    # 创建代理客户端
    client = httpx.Client(proxy=proxy_url)

    # 测试 1: 基本连接
    print("测试 1: 检查 IP 地址")
    try:
        response = client.get('http://httpbin.org/ip', timeout=10)
        result = response.json()
        print(f"✓ 代理 IP: {result.get('origin', 'Unknown')}")
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        client.close()
        return False

    # 测试 2: 访问 Google
    print("测试 2: 访问 Google")
    try:
        response = client.get('https://www.google.com', timeout=10)
        print(f"✓ Google 访问成功 (状态码: {response.status_code})")
    except Exception as e:
        print(f"✗ Google 访问失败: {e}")

    # 测试 3: 访问 GitHub
    print("测试 3: 访问 GitHub API")
    try:
        response = client.get('https://api.github.com', timeout=10)
        print(f"✓ GitHub API 访问成功 (状态码: {response.status_code})")
    except Exception as e:
        print(f"✗ GitHub API 访问失败: {e}")

    # 测试 4: DNS 解析
    print("测试 4: DNS 解析测试")
    try:
        response = client.get('http://httpbin.org/get', timeout=10)
        print(f"✓ DNS 解析正常")
    except Exception as e:
        print(f"✗ DNS 解析失败: {e}")

    client.close()

    print()
    print("=== 代理测试完成 ===")
    return True

if __name__ == "__main__":
    test_proxy_connection()
