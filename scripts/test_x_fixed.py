#!/usr/bin/env python3
"""
修正版 X 平台搜索测试
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

async def test_x_search_with_auth():
    """使用正确认证方式测试 X 平台搜索"""
    print("=" * 60)
    print(" X 平台搜索功能测试")
    print("=" * 60)

    # 检查认证信息
    username = os.getenv("TWITTER_USERNAME", "")
    email = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")
    cookies_file = os.getenv("TWITTER_COOKIES_FILE", "twitter_cookies.json")

    print(f"\n认证信息:")
    print(f"  用户名: {username}")
    print(f"  邮箱: {email}")
    print(f"  Cookies: {cookies_file}")

    if not all([username, email, password]):
        print("\n✗ 认证信息不完整")
        return False

    try:
        from twikit import Client

        print(f"\n正在连接 X 平台...")

        # 创建客户端
        client = Client(language='en')

        # 检查 cookies 文件
        cookies_path = Path("/agent-studio/agent-studio") / cookies_file

        if cookies_path.exists():
            print(f"✓ 发现 cookies 文件，尝试加载...")
            try:
                # 使用 load_cookies 方法
                client.load_cookies(str(cookies_path))
                print("✓ Cookies 加载成功")

                # 测试连接是否有效
                await client.login(
                    auth_info_1=username,
                    auth_info_2=email,
                    password=password
                )
            except Exception as e:
                print(f"Cookies 无效，重新登录: {e}")
                raise
        else:
            print("首次登录，可能需要邮箱验证...")
            # 尝试登录
            await client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password
            )
            # 保存 cookies
            client.save_cookies(str(cookies_path))
            print(f"✓ 登录成功，已保存 cookies 到 {cookies_path}")

        # 测试搜索
        print(f"\n测试搜索功能...")
        print(f"搜索查询: 'AI technology' (最多5条结果)")

        # 使用搜索方法
        tweets = await client.search('AI technology', limit=5)

        if tweets and len(tweets) > 0:
            print(f"\n✓ 搜索成功！找到 {len(tweets)} 条推文\n")

            for i, tweet in enumerate(tweets[:3], 1):
                print(f"推文 {i}:")
                print(f"  作者: @{tweet.user.screen_name}")
                print(f"  昵称: {tweet.user.name}")
                print(f"  内容: {tweet.text[:80]}...")
                print(f"  时间: {tweet.created_at}")
                print(f"  互动: 💬 {tweet.reply_count} | 🔄 {tweet.retweet_count} | ❤️ {tweet.favorite_count}")
                print()

            return True
        else:
            print("✗ 搜索未返回结果")
            return False

    except ImportError as e:
        print(f"✗ 导入错误: {e}")
        print("请安装: pip install twikit")
        return False
    except Exception as e:
        print(f"✗ 搜索失败: {e}")
        print(f"\n可能的原因:")
        print("1. 账号需要邮箱验证码 (首次登录)")
        print("2. 账号被限制或锁定")
        print("3. 网络连接问题")
        print("4. 代理设置问题")
        return False

async def test_simple_access():
    """测试基本访问能力"""
    print("\n" + "=" * 60)
    print(" 基础访问测试")
    print("=" * 60)

    try:
        import httpx

        async with httpx.AsyncClient(
            proxy="http://127.0.0.1:7890",
            timeout=15.0,
            follow_redirects=True
        ) as client:
            # 测试 X.com 访问
            response = await client.get('https://x.com')
            print(f"✓ X.com 访问: 状态码 {response.status_code}")

            if response.status_code == 200:
                print("✓ 代理连接正常")

                # 测试移动端 API
                try:
                    mobile_response = await client.get('https://mobile.twitter.com')
                    print(f"✓ 移动端访问: 状态码 {mobile_response.status_code}")
                except Exception as mobile_e:
                    print(f"ℹ️  移动端访问可能需要特殊处理")

                return True
            else:
                print(f"✗ 访问异常: {response.status_code}")
                return False

    except Exception as e:
        print(f"✗ 连接测试失败: {e}")
        return False

async def main():
    print("=" * 60)
    print(" X 平台功能验证")
    print("=" * 60)

    # 基础访问测试
    access_ok = await test_simple_access()

    # 搜索功能测试
    search_ok = await test_x_search_with_auth()

    # 总结
    print("\n" + "=" * 60)
    print(" 测试结果总结")
    print("=" * 60)
    print(f" 基础访问: {'✓ 正常' if access_ok else '✗ 异常'}")
    print(f" 搜索功能: {'✓ 正常' if search_ok else '✗ 异常'}")

    if access_ok and not search_ok:
        print("\n⚠️  网络连接正常，但认证可能需要完成")
        print("\n建议操作:")
        print("1. 首次登录可能需要邮箱验证码")
        print("2. 确保账号状态正常（未被封禁）")
        print("3. 可以尝试手动登录 x.com 网页版激活账号")
        print("4. 检查是否需要处理两步验证")
    elif search_ok:
        print("\n🎉 X 平台搜索功能完全正常！")
    else:
        print("\n❌ 网络连接存在问题，请检查代理配置")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
