#!/usr/bin/env python3
"""
简单的 YouTube 字幕提取测试
"""

import os
import sys

try:
    import youtube_transcript_api
    print("✓ youtube-transcript-api 已安装")
except ImportError:
    print("✗ youtube-transcript-api 未安装")
    sys.exit(1)

# 测试字幕提取
def test_youtube_subtitle():
    print("\n=== 测试 YouTube 字幕提取 ===")

    # 代理设置
    proxy_url = "http://127.0.0.1:7890"

    # 测试视频ID (一个关于 Python 的教学视频)
    test_video_id = "rfscVS0vtbw"  # Learn Python - Full Course for Beginners

    try:
        print(f"测试视频 ID: {test_video_id}")
        print(f"代理设置: {proxy_url}")

        # 创建客户端
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.proxies import GenericProxyConfig

        # 配置代理
        proxy_config = GenericProxyConfig(
            http_url=proxy_url,
            https_url=proxy_url
        )

        # 获取字幕
        print("正在获取字幕...")
        transcript = YouTubeTranscriptApi.get_transcript(
            test_video_id,
            proxies=proxy_config,
            languages=['zh-Hans', 'zh', 'en']
        )

        # 处理字幕文本
        full_text = " ".join([entry['text'] for entry in transcript])

        print(f"✓ 成功获取字幕")
        print(f"  字幕条数: {len(transcript)}")
        print(f"  总字符数: {len(full_text)}")
        print(f"  预览: {full_text[:150]}...")

        return True

    except Exception as e:
        print(f"✗ 获取字幕失败: {e}")
        return False

# 测试 YouTube 搜索
def test_youtube_search():
    print("\n=== 测试 YouTube 搜索功能 ===")

    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        print("✗ 缺少 YOUTUBE_API_KEY")
        return False

    print(f"✓ YOUTUBE_API_KEY 已设置: {api_key[:10]}...")

    try:
        import requests

        # 搜索参数
        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': 'Python tutorial',
            'type': 'video',
            'maxResults': 3,
            'key': api_key
        }

        proxies = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890'
        }

        print(f"正在搜索: 'Python tutorial'")
        response = requests.get(search_url, params=params, proxies=proxies, timeout=15)

        if response.status_code == 200:
            data = response.json()
            videos = data.get('items', [])

            print(f"✓ 搜索成功，找到 {len(videos)} 个视频")

            for i, video in enumerate(videos, 1):
                title = video['snippet']['title']
                channel = video['snippet']['channelTitle']
                print(f"\n  视频 {i}:")
                print(f"    标题: {title}")
                print(f"    频道: {channel}")

            return True
        else:
            print(f"✗ 搜索失败，状态码: {response.status_code}")
            print(f"  响应: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"✗ 搜索失败: {e}")
        return False

if __name__ == "__main__":
    print("YouTube 功能测试")
    print("=" * 40)

    # 检查环境变量
    if os.getenv("YOUTUBE_API_KEY"):
        print("✓ YOUTUBE_API_KEY 已设置")
    else:
        print("✗ YOUTUBE_API_KEY 未设置")

    # 运行测试
    search_ok = test_youtube_search()
    subtitle_ok = test_youtube_subtitle()

    print("\n" + "=" * 40)
    print("测试结果:")
    print(f"YouTube 搜索: {'✓ 通过' if search_ok else '✗ 失败'}")
    print(f"字幕提取: {'✓ 通过' if subtitle_ok else '✗ 失败'}")
