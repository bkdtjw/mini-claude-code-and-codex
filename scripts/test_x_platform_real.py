#!/usr/bin/env python3
"""
实际测试 X 平台搜索功能
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

async def test_x_search():
    """测试 X 平台搜索"""
    print("=" * 60)
    print(" X 平台搜索功能测试")
    print("=" * 60)

    # 检查认证信息
    username = os.getenv("TWITTER_USERNAME", "")
    email = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")
    cookies_file = os.getenv("TWITTER_COOKIES_FILE", "twitter_cookies.json")

    print(f"\n认证信息检查:")
    print(f"  用户名: {username}")
    print(f"  邮箱: {email}")
    print(f"  密码: {'已设置' if password else '未设置'}")
    print(f"  Cookies 文件: {cookies_file}")

    if not all([username, email, password]):
        print("\n✗ 认证信息不完整，无法测试")
        return False

    try:
        from twikit import Client

        print(f"\n正在初始化 X 平台客户端...")

        # 创建客户端实例
        client = Client('en')

        # 检查是否有已保存的 cookies
        cookies_path = Path("/agent-studio/agent-studio") / cookies_file

        if cookies_path.exists():
            print(f"发现已保存的 cookies，尝试加载...")
            try:
                # 尝试使用 cookies 直接登录
                await client.login(
                    auth_info_1=username,
                    auth_info_2=email,
                    password=password,
                    cookies=str(cookies_path)
                )
                print("✓ 使用 cookies 登录成功")
            except Exception as e:
                print(f"Cookies 登录失败: {e}")
                print("尝试重新登录...")
                await client.login(
                    auth_info_1=username,
                    auth_info_2=email,
                    password=password
                )
                # 保存 cookies
                client.save_cookies(str(cookies_path))
                print("✓ 重新登录成功，已保存 cookies")
        else:
            print("首次登录，需要完成认证流程...")
            print("注意：这可能需要几分钟时间")

            try:
                # 尝试登录
                await client.login(
                    auth_info_1=username,
                    auth_info_2=email,
                    password=password
                )

                # 保存 cookies 以备下次使用
                client.save_cookies(str(cookies_path))
                print("✓ 登录成功，已保存 cookies")

            except Exception as e:
                print(f"✗ 登录失败: {e}")
                print("\n可能的原因:")
                print("1. 需要邮箱验证码")
                print("2. 账号被锁定")
                print("3. 网络连接问题")
                return False

        # 测试搜索功能
        print(f"\n测试搜索功能...")
        print(f"搜索查询: 'AI technology'")

        tweets = await client.search('AI technology', limit=5)

        if tweets:
            print(f"✓ 搜索成功！找到 {len(tweets)} 条推文\n")

            for i, tweet in enumerate(tweets[:3], 1):
                print(f"推文 {i}:")
                print(f"  作者: @{tweet.user.screen_name}")
                print(f"  内容: {tweet.text[:100]}...")
                print(f"  发布时间: {tweet.created_at}")
                print(f"  互动: {tweet.reply_count} 回复, {tweet.retweet_count} 转发, {tweet.favorite_count} 点赞")
                print()

            return True
        else:
            print("✗ 搜索未返回结果")
            return False

    except ImportError as e:
        print(f"✗ 导入 twikit 失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 搜索失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_simple_search():
    """简单搜索测试"""
    print("\n" + "=" * 60)
    print(" 简单连接测试")
    print("=" * 60)

    try:
        import httpx

        # 测试基本的 X/Twitter 访问（允许重定向）
        async with httpx.AsyncClient(
            proxy="http://127.0.0.1:7890",
            timeout=15.0,
            follow_redirects=True
        ) as client:
            # 测试 X.com
            response = await client.get('https://x.com')
            print(f"✓ X.com 访问: 状态码 {response.status_code}")

            if response.status_code == 200:
                print("✓ 代理连接正常，可以访问 X 平台")

                # 测试 Twitter API 端点
                try:
                    api_response = await client.get('https://api.twitter.com/2/tweets/search/recent?query=AI', headers={
                        'User-Agent': 'Mozilla/5.0'
                    })
                    print(f"✓ Twitter API 访问: 状态码 {api_response.status_code}")
                except Exception as api_e:
                    print(f"ℹ️  Twitter API 需要认证 (这是正常的)")

                return True
            else:
                print(f"✗ X 平台访问异常: {response.status_code}")
                return False

    except Exception as e:
        print(f"✗ 连接测试失败: {e}")
        return False

async def main():
    # 先测试基本连接
    connection_ok = await test_simple_search()

    if not connection_ok:
        print("\n⚠️  警告：无法连接到 Twitter")
        print("请检查：")
        print("1. 代理服务是否运行")
        print("2. 网络连接是否正常")
        return

    # 测试搜索功能
    search_ok = await test_x_search()

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    print(f"基础连接: {'✓ 正常' if connection_ok else '✗ 异常'}")
    print(f"搜索功能: {'✓ 正常' if search_ok else '✗ 异常'}")

    if search_ok:
        print("\n🎉 X 平台搜索功能完全正常！")
    elif connection_ok:
        print("\n⚠️  网络连接正常，但搜索功能需要完成认证")
        print("建议：")
        print("1. 检查账号是否需要邮箱验证")
        print("2. 确认账号状态正常")
        print("3. 尝试手动登录一次 Twitter 网页版")

if __name__ == "__main__":
    asyncio.run(main())
