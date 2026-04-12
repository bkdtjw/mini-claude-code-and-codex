#!/usr/bin/env python3
"""
X 平台详细诊断
"""

import asyncio
import sys
import os
from pathlib import Path

# 设置代理
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

async def detailed_x_test():
    """详细的 X 平台测试"""
    print("=" * 60)
    print(" X 平台详细诊断")
    print("=" * 60)

    username = os.getenv("TWITTER_USERNAME", "")
    email = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")

    print(f"\n账号信息:")
    print(f"  用户名: {username}")
    print(f"  邮箱: {email}")
    print(f"  密码: {'已设置' if password else '未设置'}")

    if not all([username, email, password]):
        print("\n✗ 认证信息不完整，无法继续测试")
        return False

    try:
        from twikit import Client

        print(f"\n开始认证流程...")

        # 创建客户端
        client = Client(language='en')

        # 检查现有 cookies
        cookies_path = Path("/agent-studio/agent-studio/twitter_cookies.json")

        if cookies_path.exists():
            print(f"✓ 发现已存 cookies: {cookies_path}")
            print(f"  文件大小: {cookies_path.stat().st_size} bytes")
            print(f"  修改时间: {cookies_path.stat().st_mtime}")

        print(f"\n尝试登录...")
        print("这可能需要 30-60 秒，请耐心等待...")

        # 尝试登录并显示详细过程
        try:
            # 尝试登录（不使用cookies）
            await client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password
            )

            print("✓ 登录成功！")

            # 保存 cookies
            client.save_cookies(str(cookies_path))
            print(f"✓ 已保存 cookies 到 {cookies_path}")

            # 测试基本功能
            print(f"\n测试用户信息获取...")
            try:
                # 获取当前用户信息
                me = await client.user_me()
                print(f"✓ 当前用户: @{me.screen_name}")
                print(f"  名称: {me.name}")
                print(f"  粉丝数: {me.followers_count}")
                print(f"  关注数: {me.following_count}")
            except Exception as user_e:
                print(f"✗ 获取用户信息失败: {user_e}")

            # 测试搜索功能
            print(f"\n测试搜索功能...")
            try:
                tweets = await client.search('Python', limit=3)
                if tweets:
                    print(f"✓ 搜索成功！找到 {len(tweets)} 条推文")
                    for i, tweet in enumerate(tweets[:2], 1):
                        print(f"\n  推文 {i}:")
                        print(f"    作者: @{tweet.user.screen_name}")
                        print(f"    内容: {tweet.text[:60]}...")
                else:
                    print("✗ 搜索未返回结果")
            except Exception as search_e:
                print(f"✗ 搜索失败: {search_e}")

            return True

        except Exception as login_e:
            print(f"✗ 登录失败: {login_e}")
            print(f"\n错误类型: {type(login_e).__name__}")

            # 检查是否是特定的错误类型
            error_msg = str(login_e)
            if "captcha" in error_msg.lower():
                print("❌ 需要完成验证码")
            elif "suspended" in error_msg.lower():
                print("❌ 账号已被暂停")
            elif "locked" in error_msg.lower():
                print("❌ 账号已被锁定")
            elif "password" in error_msg.lower():
                print("❌ 密码错误")
            elif "email" in error_msg.lower():
                print("❌ 邮箱验证问题")
            else:
                print(f"❓ 未知错误: {error_msg}")

            return False

    except ImportError as e:
        print(f"✗ 无法导入 twikit: {e}")
        return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
        return False

async def test_proxy_connection():
    """测试代理连接"""
    print("\n" + "=" * 60)
    print(" 代理连接测试")
    print("=" * 60)

    try:
        import httpx

        async with httpx.AsyncClient(
            proxy="http://127.0.0.1:7890",
            timeout=10.0,
            follow_redirects=True
        ) as client:
            # 测试多个端点
            endpoints = [
                ('https://x.com', 'X.com 主页'),
                ('https://api.twitter.com', 'Twitter API'),
                ('https://mobile.twitter.com', '移动端'),
            ]

            for url, name in endpoints:
                try:
                    response = await client.get(url)
                    print(f"✓ {name}: 状态码 {response.status_code}")
                except Exception as e:
                    print(f"✗ {name}: 失败 - {e}")

            return True

    except Exception as e:
        print(f"✗ 代理测试失败: {e}")
        return False

async def main():
    print("=" * 60)
    print(" X 平台功能完整诊断")
    print("=" * 60)

    # 代理测试
    proxy_ok = await test_proxy_connection()

    # X 平台测试
    x_ok = await detailed_x_test()

    # 总结
    print("\n" + "=" * 60)
    print(" 诊断总结")
    print("=" * 60)
    print(f" 代理连接: {'✓ 正常' if proxy_ok else '✗ 异常'}")
    print(f" X 平台: {'✓ 正常' if x_ok else '✗ 异常'}")

    if proxy_ok and not x_ok:
        print("\n💡 建议:")
        print("1. 检查 X/Twitter 账号状态")
        print("2. 确认邮箱和密码是否正确")
        print("3. 尝试在浏览器中手动登录 x.com")
        print("4. 如有验证码要求，需要处理验证")
        print("5. 检查账号是否需要邮箱验证")
    elif x_ok:
        print("\n🎉 X 平台功能完全正常！")
        print("   可以进行推文搜索和信息获取")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被中断")
    except Exception as e:
        print(f"\n❌ 诊断过程出错: {e}")
