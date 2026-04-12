#!/usr/bin/env python3
"""
手动设置代理的 X 平台测试
"""

import asyncio
import sys
import os
from pathlib import Path

# 加载环境变量
env_path = Path("/agent-studio/agent-studio/.env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

async def test_x_with_explicit_proxy():
    """使用显式代理配置测试 X 平台"""
    print("=" * 60)
    print(" X 平台代理配置测试")
    print("=" * 60)

    username = os.getenv("TWITTER_USERNAME", "")
    email = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")

    print(f"\n账号: {username}")
    print(f"邮箱: {email}")

    if not all([username, email, password]):
        print("✗ 认证信息不完整")
        return False

    try:
        from twikit import Client
        import httpx

        print(f"\n配置代理客户端...")

        # 创建显式的代理客户端
        proxy = "http://127.0.0.1:7890"
        print(f"使用代理: {proxy}")

        # 创建带有代理配置的 httpx 客户端
        http_client = httpx.AsyncClient(
            proxy=proxy,
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )

        print("✓ HTTP 客户端创建成功")

        # 测试代理连接
        try:
            test_response = await http_client.get('https://x.com')
            print(f"✓ 代理连接测试: {test_response.status_code}")
        except Exception as test_e:
            print(f"✗ 代理连接测试失败: {test_e}")
            return False

        # 创建 twikit 客户端
        print(f"\n创建 X 平台客户端...")
        client = Client(language='en', httpx_client=http_client)

        print(f"开始登录流程...")
        print("(这可能需要 30-90 秒)")

        try:
            # 尝试登录
            await client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password
            )

            print("✓ 登录成功！")

            # 保存 cookies
            cookies_path = Path("/agent-studio/agent-studio/twitter_cookies.json")
            client.save_cookies(str(cookies_path))
            print(f"✓ 已保存 cookies")

            # 测试搜索
            print(f"\n测试搜索功能...")
            tweets = await client.search('Python programming', limit=2)

            if tweets:
                print(f"✓ 搜索成功！找到 {len(tweets)} 条推文")
                for i, tweet in enumerate(tweets, 1):
                    print(f"\n  推文 {i}:")
                    print(f"    作者: @{tweet.user.screen_name}")
                    print(f"    内容: {tweet.text[:80]}...")
                return True
            else:
                print("✗ 搜索未返回结果")
                return False

        except Exception as login_e:
            print(f"✗ 登录失败: {login_e}")
            print(f"错误类型: {type(login_e).__name__}")

            # 提供诊断信息
            error_str = str(login_e).lower()
            if "timeout" in error_str:
                print("\n⚠️  连接超时 - 可能原因:")
                print("1. 代理服务器响应慢")
                print("2. X 平台限制访问")
                print("3. 网络不稳定")
            elif "refused" in error_str:
                print("\n⚠️  连接被拒绝 - 检查代理配置")
            elif "captcha" in error_str:
                print("\n⚠️  需要验证码")
            else:
                print(f"\n⚠️  其他错误: {login_e}")

            return False

        finally:
            await http_client.aclose()

    except ImportError as e:
        print(f"✗ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    success = await test_x_with_explicit_proxy()

    print("\n" + "=" * 60)
    if success:
        print("✅ X 平台功能正常！")
    else:
        print("❌ X 平台功能测试失败")
        print("\n📝 可能的解决方案:")
        print("1. 检查代理服务器是否正常运行")
        print("2. 尝试增加超时时间")
        print("3. 检查账号是否需要邮箱验证")
        print("4. 手动登录 x.com 激活账号")
        print("5. 检查 twikit 版本是否兼容")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断")
