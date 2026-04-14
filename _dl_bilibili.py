"""
B站视频下载 - 独立进程模块
由 b_site_launcher.py 调用，单独进程运行
"""
import os
import sys
import json
import time
from pathlib import Path

from _utils import sanitize_filename

# 强制行缓冲 + UTF-8 输出
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print(f"BILI_DL_BOOT pid={os.getpid()}", flush=True)


def process(video_url, output_dir_str):
    """下载B站视频，返回视频文件路径和标题"""
    output_dir = Path(output_dir_str)
    pid = os.getpid()

    def push(event, data=""):
        msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        print(f"STATUS:{msg}", flush=True)

    def write_progress(pct):
        """写进度到进度文件，供父进程轮询"""
        with open(str(output_dir / f"_dl_progress_{pid}.txt"), 'w', encoding='utf-8') as f:
            f.write(str(int(pct)))

    try:
        push("status", "正在下载B站视频...")

        import yt_dlp

        # B站：优先用Chrome Cookie，失败则用无Cookie方式
        video_file = None
        video_title = "unknown"

        def make_ydl_opts():
            return {
                'outtmpl': str(output_dir / "%(title)s.%(ext)s"),
                'format': 'bestvideo+bestaudio/best',
                'no_resume': True,
                'ffmpeg_location': str(Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"),
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                },
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [],
            }

        def download_hook(d):
            # 只写进度文件，不再往 stdout 写 STATUS（避免和 yt_dlp stderr 混输出）
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    pct = downloaded / total * 100
                    write_progress(int(pct))
            elif d['status'] == 'finished':
                write_progress(100)

        # 方式1：Chrome Cookie
        try:
            push("status", "尝试Cookie方式...")
            ydl_opts = make_ydl_opts()
            ydl_opts['cookies-from-browser'] = 'chrome'
            ydl_opts['progress_hooks'].append(download_hook)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_title = info.get('title', 'unknown')
                video_file = output_dir / f"{video_title}.mp4"
                if not video_file.exists():
                    for f in output_dir.glob(f"{video_title}.*"):
                        if f.suffix in ['.mp4', '.mkv', '.flv']:
                            video_file = f
                            break
            write_progress(100)
            push("status", f"B站视频下载完成（Cookie）: {video_title}")
        except Exception as e_cookie:
            write_progress(0)
            push("status", f"Cookie方式失败: {e_cookie}，尝试无Cookie...")
            ydl_opts_direct = make_ydl_opts()
            ydl_opts_direct['progress_hooks'].append(download_hook)
            try:
                with yt_dlp.YoutubeDL(ydl_opts_direct) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    video_title = info.get('title', 'unknown')
                    video_file = output_dir / f"{video_title}.mp4"
                    if not video_file.exists():
                        for f in output_dir.glob(f"{video_title}.*"):
                            if f.suffix in ['.mp4', '.mkv', '.flv']:
                                video_file = f
                                break
                write_progress(100)
                push("status", f"B站视频下载完成（无Cookie）: {video_title}")
            except Exception as e2:
                return {"ok": False, "error": f"B站视频下载失败: {e2}"}

        if not video_file or not video_file.exists():
            return {"ok": False, "error": f"视频文件未找到: {video_title}"}

        file_size = video_file.stat().st_size
        if file_size < 50000:
            return {"ok": False, "error": f"下载的视频异常（小于50KB）"}

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
    print(f"BILI_DL_START pid={os.getpid()}", flush=True)
    try:
        video_url = sys.argv[1]
        output_dir = sys.argv[2]
        print(f"ARGS video_url={video_url}", flush=True)
        print(f"ARGS output_dir={output_dir}", flush=True)

        result = process(video_url, output_dir)
        print("RESULT:" + json.dumps(result, ensure_ascii=False), flush=True)

        sys.stdout.flush()
        sys.stderr.flush()
        time.sleep(0.5)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: {e}", flush=True)
        sys.exit(1)
