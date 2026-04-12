#!/usr/bin/env python3
"""
最终 YouTube 字幕测试
"""

def test_youtube_subtitle():
    print("=== YouTube 字幕提取测试 ===\n")

    try:
        # 尝试不同的 API 调用方式
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api import _transcripts

        video_id = "nluUYtejoIE"
        print(f"测试视频: {video_id}")

        # 方法1: 检查是否有 get_transcript 函数
        try:
            import youtube_transcript_api
            if hasattr(youtube_transcript_api, 'get_transcript'):
                print("使用 youtube_transcript_api.get_transcript()")
                transcript = youtube_transcript_api.get_transcript(video_id, languages=['en'])
                print(f"✓ 成功获取 {len(transcript)} 条字幕")
                print(f"示例: {transcript[0]}")
                return True
        except Exception as e:
            print(f"方法1失败: {e}")

        # 方法2: 使用 _transcripts 模块
        try:
            print("\n使用 _transcripts 模块")
            from youtube_transcript_api._transcripts import FetchedTranscript
            # 这需要正确的构建
            print("此方法需要特定构建，跳过")
        except Exception as e:
            print(f"方法2失败: {e}")

        # 方法3: 直接调用函数（如果存在）
        print("\n检查可用的函数:")
        import youtube_transcript_api as yt
        funcs = [name for name in dir(yt) if not name.startswith('_') and callable(getattr(yt, name))]
        print(f"可用函数: {funcs}")

        # 查找 get_transcript
        for func_name in funcs:
            if 'transcript' in func_name.lower():
                print(f"找到函数: {func_name}")
                func = getattr(yt, func_name)
                print(f"  函数类型: {type(func)}")
                print(f"  函数签名: {func.__doc__ if hasattr(func, '__doc__') else 'N/A'}")

        return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_youtube_subtitle()
