#!/usr/bin/env python3
"""
测试 X 平台和 YouTube 功能
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path("/agent-studio/agent-studio")
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from backend.core.s02_tools.builtin.youtube_client import search_videos, YouTubeSearchRequest, YouTubeClientError
from backend.core.s02_tools.builtin.x_client import search_x_posts, XClientConfig, XSearchOptions, XClientError

# 颜色输出
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✓{NC} {msg}")

def print_error(msg):
    print(f"{RED}✗{NC} {msg}")

def print_info(msg):
    print(f"{YELLOW}ℹ{NC} {msg}")

async def test_youtube_search():
    """测试 YouTube 搜索功能"""
    print("\n=== 测试 YouTube 搜索功能 ===")

    # 检查 API Key
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        print_error("缺少 YOUTUBE_API_KEY 环境变量")
        return False

    # 检查代理设置
    proxy_url = os.getenv("YOUTUBE_PROXY_URL", "http://127.0.0.1:7890")

    try:
        print_info(f"搜索查询: 'Python tutorial'")
        print_info(f"代理设置: {proxy_url}")

        request = YouTubeSearchRequest(
            query="Python tutorial",
            api_key=api_key,
            max_results=3,
            proxy_url=proxy_url
        )

        videos = await search_videos(request)

        print_success(f"找到 {len(videos)} 个视频")

        for i, video in enumerate(videos, 1):
            print(f"\n视频 {i}:")
            print(f"  标题: {video.title}")
            print(f"  频道: {video.channel}")
            print(f"  时长: {video.duration_seconds} 秒")
            print(f"  观看次数: {video.view_count:,}")
            print(f"  字幕长度: {len(video.subtitle_text)} 字符")

            # 显示字幕预览
            if video.subtitle_text:
                preview = video.subtitle_text[:100]
                print(f"  字幕预览: {preview}...")

        return True

    except YouTubeClientError as e:
        print_error(f"YouTube API 错误: {e}")
        return False
    except Exception as e:
        print_error(f"测试失败: {e}")
        return False

async def test_x_platform_search():
    """测试 X 平台搜索功能"""
    print("\n=== 测试 X 平台搜索功能 ===")

    # 检查认证信息
    username = os.getenv("TWITTER_USERNAME", "")
    email = os.getenv("TWITTER_EMAIL", "")
    password = os.getenv("TWITTER_PASSWORD", "")

    if not all([username, email, password]):
        print_error("缺少 X 平台认证信息 (TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD)")
        print_info("请在 .env 文件中设置这些变量")
        return False

    # 检查代理设置
    proxy_url = os.getenv("TWITTER_PROXY_URL", "http://127.0.0.1:7890")

    try:
        print_info(f"搜索查询: 'AI technology'")
        print_info(f"代理设置: {proxy_url}")
        print_info("正在登录 X 平台...")

        config = XClientConfig(
            username=username,
            email=email,
            password=password,
            proxy_url=proxy_url
        )

        options = XSearchOptions(
            max_results=5,
            search_type="latest"
        )

        posts = await search_x_posts("AI technology", config, options)

        print_success(f"找到 {len(posts)} 条推文")

        for i, post in enumerate(posts[:3], 1):  # 只显示前3条
            print(f"\n推文 {i}:")
            print(f"  作者: @{post.author_username}")
            print(f"  内容: {post.text[:100]}...")
            print(f"  发布时间: {post.created_at}")
            print(f"  互动: {post.reply_count} 回复, {post.retweet_count} 转发, {post.like_count} 点赞")

        return True

    except XClientError as e:
        print_error(f"X 平台客户端错误: {e}")
        return False
    except Exception as e:
        print_error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主测试函数"""
    print("=" * 50)
    print("X 平台和 YouTube 功能测试")
    print("=" * 50)

    # 检查环境变量
    print("\n检查环境配置:")
    if os.getenv("YOUTUBE_API_KEY"):
        print_success("YOUTUBE_API_KEY 已设置")
    else:
        print_error("YOUTUBE_API_KEY 未设置")

    if all([os.getenv("TWITTER_USERNAME"), os.getenv("TWITTER_EMAIL"), os.getenv("TWITTER_PASSWORD")]):
        print_success("X 平台认证信息已设置")
    else:
        print_error("X 平台认证信息未完整设置")

    # 运行测试
    youtube_ok = await test_youtube_search()
    x_platform_ok = await test_x_platform_search()

    # 总结
    print("\n" + "=" * 50)
    print("测试结果总结:")
    print("=" * 50)
    print(f"YouTube 功能: {'✓ 通过' if youtube_ok else '✗ 失败'}")
    print(f"X 平台功能: {'✓ 通过' if x_platform_ok else '✗ 失败'}")

    if youtube_ok or x_platform_ok:
        print("\n至少有一个功能正常工作!")
    else:
        print("\n建议检查配置和代理设置")

if __name__ == "__main__":
    asyncio.run(main())
