#!/usr/bin/env python3
"""
修正版 YouTube 字幕测试
"""

import os

# 加载环境变量
env_path = "/agent-studio/agent-studio/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

def test_subtitle_extraction():
    """测试字幕提取"""
    print("=== 测试 YouTube 字幕提取 ===\n")

    try:
        import youtube_transcript_api as yt_api

        # 测试视频 ID
        video_id = "nluUYtejoIE"

        print(f"测试视频: {video_id}")
        print("正在获取字幕...")

        # 使用正确的 API 调用方式
        transcript = yt_api.YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=['en', 'zh-Hans', 'zh']
        )

        if transcript:
            # 合并字幕文本
            full_text = " ".join([entry['text'] for entry in transcript])

            print(f"✓ 成功获取字幕")
            print(f"  字幕条数: {len(transcript)}")
            print(f"  总字符数: {len(full_text)}")
            print(f"  视频时长: {transcript[-1]['start'] + transcript[-1]['duration']:.1f} 秒")

            print(f"\n前 3 条字幕:")
            for i, entry in enumerate(transcript[:3], 1):
                print(f"  {i}. [{entry['start']:.1f}s] {entry['text']}")

            print(f"\n字幕文本预览:")
            print(f"  {full_text[:200]}...")

            return True
        else:
            print("✗ 未找到字幕")
            return False

    except Exception as e:
        print(f"✗ 字幕获取失败: {e}")
        # 检查是否是代理问题
        try:
            # 尝试不使用代理
            print("尝试不使用代理...")
            transcript = yt_api.YouTubeTranscriptApi.get_transcript(video_id)
            if transcript:
                print("✓ 不使用代理时成功获取字幕")
                return True
        except Exception as e2:
            print(f"✗ 不使用代理也失败: {e2}")
        return False

def test_with_proxy():
    """测试带代理的字幕提取"""
    print("\n=== 测试带代理的字幕提取 ===\n")

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.proxies import GenericProxyConfig

        video_id = "nluUYtejoIE"
        proxy_url = "http://127.0.0.1:7890"

        print(f"测试视频: {video_id}")
        print(f"使用代理: {proxy_url}")

        # 创建代理配置
        proxy_config = GenericProxyConfig(
            http_url=proxy_url,
            https_url=proxy_url
        )

        # 获取字幕
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=['en'],
            proxies=proxy_config
        )

        if transcript:
            print(f"✓ 使用代理成功获取字幕")
            print(f"  字幕条数: {len(transcript)}")

            # 显示前几条
            print(f"\n前 3 条字幕:")
            for i, entry in enumerate(transcript[:3], 1):
                print(f"  {i}. [{entry['start']:.1f}s] {entry['text']}")

            return True

    except Exception as e:
        print(f"✗ 带代理获取字幕失败: {e}")
        return False

def main():
    print("=" * 50)
    print("YouTube 字幕提取测试")
    print("=" * 50)

    # 测试不带代理
    result1 = test_subtitle_extraction()

    # 测试带代理
    result2 = test_with_proxy()

    print("\n" + "=" * 50)
    print("测试结果:")
    print(f"字幕提取 (无代理): {'✓ 通过' if result1 else '✗ 失败'}")
    print(f"字幕提取 (有代理): {'✓ 通过' if result2 else '✗ 失败'}")

    if result1 or result2:
        print("\n✓ YouTube 字幕提取功能正常!")
    else:
        print("\n✗ YouTube 字幕提取功能异常")

if __name__ == "__main__":
    main()
