#!/usr/bin/env python3
"""
测试 YouTube API 和字幕提取
"""

import os
import sys

# 加载 .env 文件
def load_env():
    env_path = "/agent-studio/agent-studio/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env()

# 检查 API Key
api_key = os.getenv("YOUTUBE_API_KEY", "")
if api_key:
    print(f"✓ YOUTUBE_API_KEY 已设置: {api_key[:10]}...")
else:
    print("✗ YOUTUBE_API_KEY 未设置")

def test_youtube_search():
    """测试 YouTube 搜索"""
    print("\n=== 测试 YouTube 搜索 ===")

    try:
        import requests
        import json

        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': 'Python programming tutorial',
            'type': 'video',
            'maxResults': 3,
            'key': api_key,
            'order': 'relevance'
        }

        proxies = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890'
        }

        print(f"搜索查询: 'Python programming tutorial'")
        print(f"使用代理: {proxies['http']}")

        response = requests.get(search_url, params=params, proxies=proxies, timeout=15)

        if response.status_code == 200:
            data = response.json()
            videos = data.get('items', [])

            print(f"✓ 搜索成功，找到 {len(videos)} 个视频\n")

            for i, video in enumerate(videos, 1):
                video_id = video['id']['videoId']
                title = video['snippet']['title']
                channel = video['snippet']['channelTitle']
                description = video['snippet']['description'][:100]

                print(f"视频 {i}:")
                print(f"  ID: {video_id}")
                print(f"  标题: {title}")
                print(f"  频道: {channel}")
                print(f"  描述: {description}...")
                print()

            # 返回第一个视频ID用于字幕测试
            if videos:
                return videos[0]['id']['videoId']
        else:
            print(f"✗ 搜索失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text[:300]}")

        return None

    except Exception as e:
        print(f"✗ 搜索异常: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_youtube_subtitle(video_id):
    """测试字幕提取"""
    print(f"\n=== 测试字幕提取 (视频: {video_id}) ===")

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.proxies import GenericProxyConfig

        proxy_config = GenericProxyConfig(
            http_url="http://127.0.0.1:7890",
            https_url="http://127.0.0.1:7890"
        )

        print("正在获取字幕...")

        # 尝试获取中文字幕
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxy_config)
            print(f"✓ 找到字幕列表")

            # 显示可用语言
            for transcript in transcript_list:
                print(f"  - {transcript.language_code} ({transcript.language})")

            # 获取第一个可用字幕
            transcript = transcript_list.find_transcript(['en', 'zh-Hans', 'zh'])
            transcript_data = transcript.fetch()

            # 合并字幕文本
            full_text = " ".join([entry['text'] for entry in transcript_data])

            print(f"\n✓ 成功获取字幕")
            print(f"  字幕条数: {len(transcript_data)}")
            print(f"  总字符数: {len(full_text)}")
            print(f"  时长: {transcript_data[-1]['start'] + transcript_data[-1]['duration']:.1f} 秒")
            print(f"\n字幕预览:")
            print(f"  {full_text[:200]}...")

            return True

        except Exception as e:
            print(f"✗ 字幕获取失败: {e}")
            return False

    except ImportError as e:
        print(f"✗ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"✗ 字幕测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 50)
    print("YouTube 功能完整测试")
    print("=" * 50)

    if not api_key:
        print("\n⚠️  警告: 未设置 YOUTUBE_API_KEY")
        print("请设置有效的 YouTube Data API v3 密钥")
        print("获取地址: https://console.cloud.google.com/")
        return

    # 测试搜索
    video_id = test_youtube_search()

    # 测试字幕
    if video_id:
        test_youtube_subtitle(video_id)
    else:
        # 使用默认测试视频
        print("使用默认测试视频...")
        test_youtube_subtitle("rfscVS0vtbw")

if __name__ == "__main__":
    main()
