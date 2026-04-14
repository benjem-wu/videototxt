"""
B站视频下载 - 独立进程模块
由 b_site_launcher.py 调用，单独进程运行
"""
import os
import sys
import json
import time
import threading
from pathlib import Path

from _utils import sanitize_filename, validate_video_file, cleanup_part_files, find_and_rename_dl_file

# 强制行缓冲 + UTF-8 输出
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')
sys.stderr.reconfigure(line_buffering=True, encoding='utf-8', errors='replace')

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

        # 下载前清理残留 .part 文件
        cleanup_part_files(output_dir)

        import yt_dlp

        video_file = None
        video_title = "unknown"

        def make_ydl_opts():
            return {
                'outtmpl': str(output_dir / f"dl{pid}_tmp.%(ext)s"),
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
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    pct = downloaded / total * 100
                    write_progress(int(pct))
            elif d['status'] == 'finished':
                write_progress(100)

        # 方式1：Chrome Cookie（最多25秒，超时直接 kill 并切无Cookie）
        cookie_ok = False
        for attempt in range(2):
            try:
                push("status", f"尝试Cookie方式...（第{attempt+1}次）")
                ydl_opts = make_ydl_opts()
                ydl_opts['cookies-from-browser'] = 'chrome'
                ydl_opts['progress_hooks'].append(download_hook)

                # 用独立线程运行 yt_dlp，每次 cookie 提取最多等 25 秒
                result_holder = [None]   # (ok, title, file_or_error)
                exc_holder = [None]

                def run_ydl():
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(video_url, download=True)
                            title = info.get('title', 'unknown')
                            vfile = find_and_rename_dl_file(pid, title, output_dir)
                        result_holder[0] = (True, title, vfile)
                    except Exception as e:
                        exc_holder[0] = e

                t = threading.Thread(target=run_ydl)
                t.start()
                t.join(timeout=25)
                if t.is_alive():
                    push("status", f"Cookie提取超时（25秒），强制切换无Cookie模式")
                    # 子线程仍在运行，忽略即可（yt_dlp 内部会自行终止）
                    break
                if exc_holder[0]:
                    raise exc_holder[0]
                ok, video_title, video_file = result_holder[0]
                write_progress(100)
                push("status", f"B站视频下载完成（Cookie）: {video_title}")
                cookie_ok = True
                break
            except Exception as e_cookie:
                if attempt < 1:
                    write_progress(0)
                    push("status", f"Cookie方式第{attempt+1}次失败: {e_cookie}，重试中...")
                    time.sleep(2)
                    continue
                write_progress(0)
                push("status", f"Cookie方式全部失败，尝试无Cookie...")

        # 方式2：无Cookie兜底（仅在Cookie失败时执行）
        if not cookie_ok:
            try:
                ydl_opts_direct = make_ydl_opts()
                ydl_opts_direct['progress_hooks'].append(download_hook)
                with yt_dlp.YoutubeDL(ydl_opts_direct) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    video_title = info.get('title', 'unknown')
                    video_file = find_and_rename_dl_file(pid, video_title, output_dir)
                write_progress(100)
                push("status", f"B站视频下载完成（无Cookie）: {video_title}")
            except Exception as e2:
                return {"ok": False, "error": f"B站视频下载失败: {e2}"}

        # 校验文件
        if not video_file or not video_file.exists():
            return {"ok": False, "error": f"视频文件未找到: {video_title}"}

        ok, err = validate_video_file(
            video_file,
            Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
        )
        if not ok:
            return {"ok": False, "error": f"视频文件校验失败: {err}"}

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
