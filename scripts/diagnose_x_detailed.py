#!/usr/bin/env python3
"""
详细的 X 平台环境诊断
"""

import asyncio
import os
import sys
import platform
from pathlib import Path

# 设置代理
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

async def diagnose_x_platform():
    """详细诊断 X 平台问题"""
    print("=" * 70)
    print(" X 平台环境诊断")
    print("=" * 70)

    # 系统信息
    print(f"\n📋 系统信息:")
    print(f"  操作系统: {platform.system()} {platform.release()}")
    print(f"  Python 版本: {sys.version}")
    print(f"  架构: {platform.machine()}")

    # 检查关键依赖
    print(f"\n📦 关键依赖:")
    try:
        import twikit
        print(f"  twikit: ✅ {twikit.__version__}")
    except ImportError as e:
        print(f"  twikit: ❌ {e}")
        return False

    try:
        import httpx
        print(f"  httpx: ✅ {httpx.__version__}")
    except ImportError as e:
        print(f"  httpx: ❌ {e}")

    try:
        import httpcore
        print(f"  httpcore: ✅ {httpcore.__version__}")
    except ImportError as e:
        print(f"  httpcore: ❌ {e}")

    # Cookies 检查
    cookies_file = Path("/agent-studio/agent-studio/twitter_cookies.json")
    print(f"\n🍪 Cookies 文件:")
    print(f"  路径: {cookies_file}")
    print(f"  存在: {'✅' if cookies_file.exists() else '❌'}")

    if cookies_file.exists():
        import json
        import time
        from datetime import datetime

        stat = cookies_file.stat()
        print(f"  大小: {stat.st_size} bytes")
        print(f"  修改时间: {datetime.fromtimestamp(stat.st_mtime)}")

        # 检查 cookies 内容
        try:
            with open(cookies_file) as f:
                cookies = json.load(f)

            print(f"  JSON 格式: ✅ 有效")
            print(f"  键数量: {len(cookies)}")

            # 检查关键 cookies
            required_keys = ['auth_token', 'ct0', 'twid']
            for key in required_keys:
                if key in cookies:
                    value = cookies[key]
                    if key == 'auth_token':
                        print(f"  {key}: ✅ 存在 (长度: {len(value)})")
                    else:
                        print(f"  {key}: ✅ 存在")
                else:
                    print(f"  {key}: ❌ 缺失")

        except Exception as e:
            print(f"  读取失败: {e}")
            return False

    # 代理检查
    print(f"\n🌐 代理配置:")
    print(f"  HTTP_PROXY: {os.getenv('HTTP_PROXY', '未设置')}")
    print(f"  HTTPS_PROXY: {os.getenv('HTTPS_PROXY', '未设置')}")

    # 测试代理连接
    print(f"\n🔗 网络连接测试:")
    try:
        import httpx

        async with httpx.AsyncClient(
            proxy="http://127.0.0.1:7890",
            timeout=10.0,
            follow_redirects=True
        ) as client:
            # 测试 X.com
            response = await client.get('https://x.com')
            print(f"  X.com: ✅ {response.status_code}")

            # 测试 API 端点
            try:
                api_response = await client.get('https://api.twitter.com/1.1/guest/activate.json')
                print(f"  Twitter API: ✅ {api_response.status_code}")
            except Exception as api_e:
                print(f"  Twitter API: ⚠️  {api_e}")

    except Exception as e:
        print(f"  网络测试: ❌ {e}")

    # Twikit 客户端测试
    print(f"\n🧪 Twikit 客户端测试:")

    try:
        from twikit import Client

        print(f"  创建客户端...")
        client = Client(
            language='en',
            proxy='http://127.0.0.1:7890'
        )
        print(f"  客户端创建: ✅")

        print(f"  加载 cookies...")
        client.load_cookies(str(cookies_file))
        print(f"  Cookies 加载: ✅")

        # 测试各种方法
        print(f"\n  测试 API 方法:")

        # 方法1: search_tweet (异步)
        try:
            print(f"    尝试 search_tweet...")
            tweets = await client.search_tweet(
                query='test',
                product='Latest',
                count=1
            )
            print(f"    search_tweet: ✅ 成功")
            if tweets:
                print(f"    返回结果: {len(tweets)} 条")
            return True

        except Exception as search_e:
            error_str = str(search_e)
            print(f"    search_tweet: ❌ {error_str[:100]}")

            # 分析错误
            if "KEY_BYTE" in error_str:
                print(f"\n  🔍 问题分析:")
                print(f"     这是 twikit 在处理 X 平台事务时的已知问题")
                print(f"     通常由于 X 平台前端代码更新导致")

                # 尝试解决方案：使用不同的方法
                print(f"\n  💡 尝试解决方案:")

                # 方案1: 使用同步方法
                try:
                    print(f"     方案1: 使用同步方法...")
                    # 这可能不适用于当前情况
                except Exception as sync_e:
                    print(f"       同步方法: ❌")

                # 方案2: 重新初始化客户端
                try:
                    print(f"     方案2: 重新初始化客户端...")
                    client2 = Client(
                        language='en',
                        proxy='http://127.0.0.1:7890'
                    )
                    client2.load_cookies(str(cookies_file))

                    # 尝试获取时间线
                    timeline = await client2.get_timeline(limit=1)
                    print(f"       get_timeline: ✅ 成功")
                    return True

                except Exception as timeline_e:
                    print(f"       get_timeline: ❌ {timeline_e}")

            elif "401" in error_str or "Unauthorized" in error_str:
                print(f"\n  🔍 问题分析:")
                print(f"     认证失败 - Cookies 可能已过期")

            elif "timeout" in error_str.lower():
                print(f"\n  🔍 问题分析:")
                print(f"     连接超时 - 网络或代理问题")

            return False

    except Exception as e:
        print(f"  客户端创建: ❌ {e}")
        return False

async def main():
    success = await diagnose_x_platform()

    print("\n" + "=" * 70)
    print("📊 诊断结果")
    print("=" * 70)

    if success:
        print("✅ X 平台功能完全正常")
    else:
        print("⚠️  X 平台功能存在问题")
        print("\n🔧 可能的解决方案:")
        print("1. 检查是否是 Windows/Linux 环境差异")
        print("2. 确认在 Windows 下使用的 twikit 版本")
        print("3. 尝试在 Linux 下使用相同的配置")
        print("4. 检查是否有额外的系统依赖")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\n❌ 诊断出错: {e}")
