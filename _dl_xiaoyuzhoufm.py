"""
小宇宙播客下载 - 独立进程模块
由 b_site_launcher.py 调用，单独进程运行
yt_dlp 直接下载（纯音频 m4a）
"""
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # 禁用GPU

import sys
import re
import json
from pathlib import Path

from _utils import sanitize_filename, validate_video_file, cleanup_part_files, find_and_rename_dl_file

# 强制行缓冲 + UTF-8 输出
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')
sys.stderr.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')

print(f"XYZ_DL_BOOT pid={os.getpid()}", flush=True)


def process(video_url, output_dir_str):
    """下载小宇宙播客音频"""
    output_dir = Path(output_dir_str)
    pid = os.getpid()

    def push(event, data=""):
        msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        print(f"STATUS:{msg}", flush=True)

    def write_progress(pct):
        with open(str(output_dir / f"_dl_progress_{pid}.txt"), 'w', encoding='utf-8') as f:
            f.write(str(int(pct)))

    try:
        push("status", "正在下载小宇宙播客...")

        # 下载前清理残留 .part 文件
        cleanup_part_files(output_dir)

        # 方式1：yt_dlp（直接可用）
        import yt_dlp

        def download_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    pct = downloaded / total * 100
                    write_progress(int(pct))
                    if int(pct) % 10 == 0:
                        push("status", f"音频下载中: {int(pct)}%")
            elif d['status'] == 'finished':
                push("status", "音频下载完成，合并中...")

        ydl_opts = {
            'outtmpl': str(output_dir / f"dl{pid}_tmp.%(ext)s"),
            'format': 'bestaudio/best',
            'no_resume': True,
            'ffmpeg_location': str(Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                'Referer': 'https://www.xiaoyuzhoufm.com/',
            },
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [download_hook],
        }

        video_file = None
        video_title = "unknown"

        try:
            push("status", "[1%] yt_dlp方式尝试...")
            write_progress(1)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_title = info.get('title', 'unknown')
                video_file = find_and_rename_dl_file(pid, video_title, output_dir)
            write_progress(100)
            push("status", f"[100%] yt_dlp下载完成: {video_title}")
        except Exception as e_yt:
            push("status", f"yt_dlp失败: {e_yt}")
            return {"ok": False, "error": f"小宇宙播客下载失败: {e_yt}"}

        if not video_file or not video_file.exists():
            return {"ok": False, "error": f"音频文件未找到: {video_title}"}

        ok, err = validate_video_file(
            video_file,
            Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
        )
        if not ok:
            video_file.unlink(missing_ok=True)
            return {"ok": False, "error": f"音频文件校验失败: {err}"}

        # 清理进度文件
        try:
            (output_dir / f"_dl_progress_{pid}.txt").unlink()
        except Exception:
            pass

        return {
            "ok": True,
            "file": str(video_file),
            "title": video_title,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    print(f"XYZ_DL_START pid={os.getpid()}", flush=True)
    try:
        video_url = sys.argv[1]
        output_dir = sys.argv[2]
        print(f"ARGS video_url={video_url}", flush=True)
        print(f"ARGS output_dir={output_dir}", flush=True)

        result = process(video_url, output_dir)
        print(f"RESULT:{json.dumps(result, ensure_ascii=False)}", flush=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"RESULT:{json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False)}", flush=True)