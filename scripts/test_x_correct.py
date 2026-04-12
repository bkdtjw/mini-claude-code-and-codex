#!/usr/bin/env python3
"""
使用正确 API 的 X 平台测试
"""

import asyncio
import sys
import os
from pathlib import Path

# 设置代理环境变量（twikit 使用这些）
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

# 加载环境变量
env_path = Path("/agent-studio/agent-studio/.env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

async def test_x_platform():
    """使用正确的 twikit API 测试"""
    print("=" * 60)
    print(" X 平台功能测试 (v2.3.3)")
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

        print(f"\n创建客户端...")
        print(f"代理设置: HTTP_PROXY={os.getenv('HTTP_PROXY')}")

        # 创建客户端（使用环境变量中的代理）
        client = Client(language='en')

        print(f"开始登录流程...")
        print("(这可能需要 30-90 秒，请耐心等待)")

        try:
            # 使用正确的登录方法
            await client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password,
                wait_for_activation=False  # 不等待激活
            )

            print("✓ 登录成功！")

            # 保存 cookies
            cookies_path = Path("/agent-studio/agent-studio/twitter_cookies.json")
            client.save_cookies(str(cookies_path))
            print(f"✓ 已保存 cookies")

            # 测试搜索
            print(f"\n测试搜索功能...")
            tweets = await client.search('AI technology', limit=3)

            if tweets and len(tweets) > 0:
                print(f"✓ 搜索成功！找到 {len(tweets)} 条推文\n")

                for i, tweet in enumerate(tweets, 1):
                    print(f"推文 {i}:")
                    print(f"  👤 @{tweet.user.screen_name} ({tweet.user.name})")
                    print(f"  📝 {tweet.text[:100]}...")
                    print(f"  📅 {tweet.created_at}")
                    print(f"  💬 {tweet.reply_count} | 🔄 {tweet.retweet_count} | ❤️ {tweet.favorite_count}")
                    print()

                return True
            else:
                print("✗ 搜索未返回结果")
                return False

        except Exception as login_e:
            print(f"✗ 登录失败: {login_e}")
            print(f"错误类型: {type(login_e).__name__}")

            error_str = str(login_e).lower()

            if "timeout" in error_str:
                print("\n⚠️  连接超时")
                print("解决方案:")
                print("1. 检查代理服务器状态")
                print("2. 尝试重启 mihomo 代理")
                print("3. 检查网络连接")
            elif "captcha" in error_str:
                print("\n⚠️  需要验证码")
                print("解决方案: 在浏览器中手动登录一次")
            elif "suspended" in error_str:
                print("\n⚠️  账号被暂停")
                print("解决方案: 检查账号状态")
            elif "verification" in error_str or "confirm" in error_str:
                print("\n⚠️  需要邮箱验证")
                print("解决方案: 检查邮箱并完成验证")
            else:
                print(f"\n⚠️  未知错误: {login_e}")

            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_basic_connection():
    """测试基本连接"""
    print("\n" + "=" * 60)
    print(" 基础连接测试")
    print("=" * 60)

    try:
        import httpx

        proxy = "http://127.0.0.1:7890"
        async with httpx.AsyncClient(
            proxy=proxy,
            timeout=15.0,
            follow_redirects=True
        ) as client:
            response = await client.get('https://x.com')
            print(f"✓ X.com 访问: {response.status_code}")
            return response.status_code == 200

    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False

async def main():
    print("=" * 60)
    print(" X 平台完整功能测试")
    print("=" * 60)
    print(f"twikit 版本: 2.3.3")
    print(f"代理设置: {os.getenv('HTTP_PROXY')}")

    # 基础连接测试
    conn_ok = await test_basic_connection()

    # X 平台测试
    x_ok = await test_x_platform()

    # 总结
    print("\n" + "=" * 60)
    print(" 测试结果总结")
    print("=" * 60)
    print(f" 基础连接: {'✓ 正常' if conn_ok else '✗ 异常'}")
    print(f" X 平台搜索: {'✓ 正常' if x_ok else '✗ 异常'}")

    if conn_ok and not x_ok:
        print("\n💡 诊断结果:")
        print("✓ 网络连接正常，代理工作正常")
        print("✗ X 平台认证存在问题")
        print("\n📋 建议:")
        print("1. 确认账号密码正确")
        print("2. 在浏览器中登录 x.com 激活账号")
        print("3. 检查是否需要邮箱验证")
        print("4. 确认账号未被限制")
        print("5. 如果是新账号，可能需要完成注册流程")
    elif x_ok:
        print("\n🎉 X 平台功能完全正常！")
        print("   支持推文搜索和信息获取")
    else:
        print("\n❌ 网络连接存在问题")
        print("   请检查代理配置")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被中断")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
