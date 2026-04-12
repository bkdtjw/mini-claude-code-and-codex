#!/usr/bin/env python3
"""
使用完全正确 API 的 X 平台测试
"""

import asyncio
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

async def test_x_final():
    """最终版本 X 平台测试"""
    print("=" * 60)
    print(" X 平台搜索功能 - 最终测试")
    print("=" * 60)

    username = os.getenv("TWITTER_USERNAME", "")
    email = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")

    print(f"\n账号信息:")
    print(f"  用户名: {username}")
    print(f"  邮箱: {email}")

    if not all([username, email, password]):
        print("\n✗ 认证信息不完整")
        return False

    try:
        from twikit import Client

        print(f"\n创建客户端...")
        # 使用正确的 API：直接传 proxy 参数
        client = Client(
            language='en',
            proxy='http://127.0.0.1:7890'
        )

        print(f"开始登录...")
        print("(这需要 30-90 秒，请耐心等待)")

        try:
            # 使用正确的登录方法（只需要三个参数）
            await client.login(
                username,  # auth_info_1
                email,     # auth_info_2
                password   # password
            )

            print("\n✓ 登录成功！")

            # 保存 cookies
            cookies_path = Path("/agent-studio/agent-studio/twitter_cookies.json")
            client.save_cookies(str(cookies_path))
            print(f"✓ 已保存 cookies 到 {cookies_path}")

            # 获取当前用户信息
            print(f"\n获取用户信息...")
            try:
                me = await client.user_me()
                print(f"✓ 当前用户: @{me.screen_name}")
                print(f"  名称: {me.name}")
                print(f"  粉丝: {me.followers_count:,}")
            except Exception as user_e:
                print(f"⚠️  获取用户信息: {user_e}")

            # 测试搜索功能
            print(f"\n测试搜索功能...")
            print(f"搜索: 'Python programming'")

            tweets = await client.search('Python programming', limit=3)

            if tweets and len(tweets) > 0:
                print(f"\n✓ 搜索成功！找到 {len(tweets)} 条推文\n")

                for i, tweet in enumerate(tweets, 1):
                    print(f"推文 {i}:")
                    print(f"  👤 @{tweet.user.screen_name} ({tweet.user.name})")
                    print(f"  📝 {tweet.text[:120]}...")
                    print(f"  📅 {tweet.created_at}")
                    print(f"  💬 {tweet.reply_count} | 🔄 {tweet.retweet_count} | ❤️ {tweet.favorite_count}")
                    print()

                print("=" * 60)
                print("✅ X 平台搜索功能完全正常！")
                print("   支持推文搜索和信息获取")
                return True
            else:
                print("✗ 搜索未返回结果")
                return False

        except Exception as login_e:
            print(f"\n✗ 登录失败: {login_e}")
            print(f"错误类型: {type(login_e).__name__}")

            error_str = str(login_e).lower()

            if "timeout" in error_str or "timed out" in error_str:
                print("\n⚠️  连接超时")
                print("   可能原因：代理服务器响应慢或网络不稳定")
            elif "captcha" in error_str:
                print("\n⚠️  需要验证码")
                print("   建议：在浏览器中登录一次 x.com")
            elif "suspended" in error_str:
                print("\n⚠️  账号被暂停")
                print("   建议：检查账号状态")
            elif "locked" in error_str:
                print("\n⚠️  账号被锁定")
                print("   建议：验证手机号或邮箱")
            elif "verification" in error_str or "confirm" in error_str:
                print("\n⚠️  需要邮箱验证")
                print("   建议：检查邮箱并完成验证")
            elif "invalid" in error_str or "incorrect" in error_str:
                print("\n⚠️  用户名/邮箱/密码错误")
                print("   建议：检查认证信息是否正确")
            else:
                print(f"\n⚠️  未知错误: {login_e}")
                print("   建议：检查网络和代理设置")

            return False

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        return False

async def main():
    success = await test_x_final()

    if not success:
        print("\n" + "=" * 60)
        print("📋 X 平台功能状态总结")
        print("=" * 60)
        print("✗ X 平台搜索功能当前不可用")
        print("\n💡 可能的原因和解决方案:")
        print("1. 账号需要邮箱验证 - 检查邮箱")
        print("2. 账号被限制 - 在浏览器中登录检查")
        print("3. 密码错误 - 确认密码正确")
        print("4. 网络问题 - 检查代理状态")
        print("5. 新账号 - 需要完成注册流程")
        print("\n🔧 临时解决方案:")
        print("- 可以使用 YouTube 功能进行视频搜索")
        print("- 等待账号问题解决后再使用 X 平台")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
