"""
小红书视频下载 - 独立进程模块
由 b_site_launcher.py 调用，单独进程运行
yt_dlp 失败则 fallback 到 Playwright 浏览器方式
"""
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''  # 禁用GPU

import sys
import asyncio
import re
import json
import time
import urllib.request
from pathlib import Path

from _utils import sanitize_filename, validate_video_file, cleanup_part_files

# 强制行缓冲 + UTF-8 输出
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print(f"XHS_DL_BOOT pid={os.getpid()}", flush=True)


def process(video_url, output_dir_str):
    """下载小红书视频：yt_dlp 优先，Playwright 兜底"""
    output_dir = Path(output_dir_str)
    pid = os.getpid()

    def push(event, data=""):
        msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        print(f"STATUS:{msg}", flush=True)

    def write_progress(pct):
        try:
            with open(str(output_dir / f"_dl_progress_{pid}.txt"), 'w', encoding='utf-8') as f:
                f.write(str(int(pct)))
        except:
            pass

    try:
        push("status", "正在下载小红书视频...")

        # 下载前清理残留 .part 文件
        cleanup_part_files(output_dir)

        # ---- 方式1：yt_dlp ----
        import yt_dlp

        def download_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    pct = downloaded / total * 100
                    write_progress(int(pct))
                    if int(pct) % 10 == 0:
                        push("status", f"视频下载中: {int(pct)}%")
            elif d['status'] == 'finished':
                push("status", "视频下载完成，合并中...")

        video_file = None
        video_title = "xiaohongshu_video"

        try:
            push("status", "[1%] yt_dlp方式尝试...")
            write_progress(1)

            ydl_opts = {
                'outtmpl': str(output_dir / "%(title)s.%(ext)s"),
                'format': 'bestvideo+bestaudio/best',
                'no_resume': True,
                'ffmpeg_location': str(Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"),
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                    'Referer': 'https://www.xiaohongshu.com/',
                },
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [download_hook],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_title = info.get('title', 'xiaohongshu_video')
                video_file = output_dir / f"{video_title}.mp4"
                if not video_file.exists():
                    for f in output_dir.glob(f"{video_title}.*"):
                        if f.suffix in ['.mp4', '.mkv', '.flv']:
                            video_file = f
                            break

            write_progress(100)
            push("status", f"[100%] yt_dlp下载完成: {video_title}")

        except Exception as e_yt:
            write_progress(0)
            push("status", f"yt_dlp失败: {e_yt}，尝试Playwright...")

            # ---- 方式2：Playwright ----
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                write_progress(10)
                push("status", "[10%] 启动浏览器...")
                video_data = loop.run_until_complete(
                    _fetch_video_data(video_url, output_dir))
                loop.close()

                video_url_found = video_data.get("video_url")
                video_title = video_data.get("title", "xiaohongshu_video")

                if not video_url_found:
                    return {"ok": False, "error": f"无法获取小红书视频地址"}

                write_progress(60)
                push("status", "[60%] 获取到视频地址，下载中...")
                video_file = output_dir / f"{video_title}.mp4"
                _download_file(video_url_found, str(video_file), video_title)
                write_progress(100)
                push("status", "[100%] Playwright下载完成")

            except Exception as e_pw:
                return {"ok": False, "error": f"小红书视频下载失败: {e_pw}"}

        if not video_file or not video_file.exists():
            return {"ok": False, "error": f"视频文件未找到: {video_title}"}

        ok, err = validate_video_file(
            video_file,
            Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
        )
        if not ok:
            video_file.unlink(missing_ok=True)
            return {"ok": False, "error": f"视频文件校验失败: {err}"}

        # 清理进度文件
        try:
            (output_dir / f"_dl_progress_{pid}.txt").unlink()
        except:
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


async def _fetch_video_data(video_url, output_dir):
    """用 Playwright 获取小红书视频直链和标题"""
    from playwright.async_api import async_playwright

    _pw_browsers_path = Path(os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(Path.home() / "AppData" / "Local" / "ms-playwright")
    ))
    _chromium_exe = _pw_browsers_path / "chromium_headless_shell-1208" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    if not _chromium_exe.exists():
        _chromium_exe = _pw_browsers_path / "chromium-1208" / "chrome-win64" / "chrome.exe"

    DESKTOP_UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )

    video_url_found = None
    video_title = "xiaohongshu_video"

    async with async_playwright() as pw:
        print("PLAYWRIGHT_LAUNCH", flush=True)
        browser = await pw.chromium.launch(
            headless=True,
            executable_path=str(_chromium_exe),
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        print("BROWSER_LAUNCHED", flush=True)

        context = await browser.new_context(
            user_agent=DESKTOP_UA,
            locale='zh-CN',
            viewport={'width': 1280, 'height': 720},
        )
        page = await context.new_page()

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
        """)
        print("CONTEXT_CREATED", flush=True)

        print(f"GOTO {video_url}", flush=True)
        try:
            await page.goto(video_url, wait_until='domcontentloaded', timeout=30000)
            print("PAGE_LOADED", flush=True)
        except Exception as e:
            print(f"PAGE_GOTO_ERROR: {e}", flush=True)

        # 等待页面完全加载（小红书JS渲染需要时间）
        await page.wait_for_timeout(5000)
        await page.evaluate('window.scrollBy(0, 400)')
        await page.wait_for_timeout(5000)

        # 拦截含视频的 API 响应
        async def handle_response(response):
            nonlocal video_url_found
            url = response.url
            # 小红书视频 API
            if any(k in url for k in ['/fe_api/', '/api/sns/', 'video', 'stream', 'mp4']):
                if 'http' in url and not video_url_found:
                    print(f"VIDEO_API_RESPONSE: {url[:200]}", flush=True)
                    video_url_found = url

        page.on("response", handle_response)
        await page.wait_for_timeout(3000)

        # 从 HTML 中提取
        html = await page.content()
        video_url_found = _extract_video_from_html(html) or video_url_found

        # 从 video 元素获取
        if not video_url_found:
            try:
                video_el = await page.query_selector('video')
                if video_el:
                    src = await video_el.get_attribute('src')
                    if src and 'http' in src and not src.startswith('blob:'):
                        video_url_found = src
                        print(f"VIDEO_ELEMENT: {src[:150]}", flush=True)
            except Exception as e:
                print(f"VIDEO_ELEMENT_ERROR: {e}", flush=True)

        # 获取标题
        for sel in ['h1', '.title', '[data-v-title]', '.note-content .title']:
            try:
                el = await page.query_selector(sel)
                if el:
                    t = await el.inner_text()
                    if t and t.strip():
                        video_title = sanitize_filename(t.strip())
                        break
            except:
                pass

        await browser.close()
        print(f"RESULT video_url={bool(video_url_found)} title={video_title[:50]}", flush=True)

    return {"video_url": video_url_found, "title": video_title}


def _extract_video_from_html(html):
    """从页面 HTML 中提取视频直链"""
    patterns = [
        r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*sns-video[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*byteimg\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*lsy\.xiaohongshu\.com[^\s"\'<>]*',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            url = m.group(0).split('"')[0].split("'")[0].split('?')[0]
            import html as html_module
            url = html_module.unescape(url)
            if '.mp4' in url or 'video' in url.lower():
                print(f"HTML_VIDEO_FOUND: {url[:150]}", flush=True)
                return url

    # JSON 字段
    for pat in [
        r'"videoUrl"\s*:\s*"([^"]+)"',
        r'"streamUrl"\s*:\s*"([^"]+)"',
        r'"playUrl"\s*:\s*"([^"]+)"',
    ]:
        m = re.search(pat, html)
        if m:
            url = m.group(1)
            if url.startswith('//'):
                url = 'https:' + url
            if url.startswith('http'):
                print(f"JSON_VIDEO_FOUND: {url[:150]}", flush=True)
                return url

    return None


def _download_file(url, output_path_str, title):
    """下载文件到本地"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Referer': 'https://www.xiaohongshu.com/',
    }
    req = urllib.request.Request(url, headers=headers)
    print(f"DOWNLOAD_START: {url[:100]}", flush=True)
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(output_path_str, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    print(f"DOWNLOAD_DONE size={Path(output_path_str).stat().st_size/1024/1024:.1f}MB", flush=True)


if __name__ == "__main__":
    print(f"XHS_DL_START pid={os.getpid()}", flush=True)
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
