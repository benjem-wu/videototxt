"""
抖音视频下载 - 独立进程模块
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

from _utils import sanitize_filename

# 强制行缓冲 + UTF-8 输出
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print(f"DY_DL_BOOT pid={os.getpid()}", flush=True)


async def _playwright_download(video_url, video_id, output_dir):
    """用 Playwright 渲染抖音页面，拦截视频流请求实时获取 URL 并下载"""
    from playwright.async_api import async_playwright

    _pw_browsers_path = Path(os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(Path.home() / "AppData" / "Local" / "ms-playwright")
    ))
    # 优先用轻量的 headless shell，启动更快
    _chromium_exe = _pw_browsers_path / "chromium_headless_shell-1208" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    if not _chromium_exe.exists():
        _chromium_exe = _pw_browsers_path / "chromium-1208" / "chrome-win64" / "chrome.exe"

    # 使用桌面 Chrome UA，桌面版抖音页面
    DESKTOP_UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )

    video_api_url = None
    video_title = f"douyin_{video_id}"

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

        # 防检测
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
                if (p === 37445) return 'Intel Inc.';
                if (p === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.apply(this, arguments);
            };
        """)
        print("CONTEXT_CREATED", flush=True)

        # 拦截视频 API 响应，找到视频真实地址
        async def handle_response(response):
            nonlocal video_api_url
            url = response.url
            if '/aweme/v1/playwm/' in url or '/aweme/v1/play/' in url or 'video_bytededef' in url:
                print(f"VIDEO_API_RESPONSE: {url[:200]}", flush=True)
                video_api_url = url

        page.on("response", handle_response)

        # video_id 为 None 说明短链接未能解析，直接用短链接让浏览器跳转
        navigate_url = f'https://www.douyin.com/video/{video_id}' if video_id else video_url
        print(f"GOTO {navigate_url}", flush=True)
        try:
            await page.goto(navigate_url, wait_until='domcontentloaded', timeout=30000)
            print("PAGE_LOADED", flush=True)
        except Exception as e:
            print(f"PAGE_GOTO_ERROR: {e}", flush=True)
        print("WAIT_SCROLL", flush=True)
        await page.wait_for_timeout(3000)
        await page.evaluate('window.scrollBy(0, 300)')
        await page.wait_for_timeout(3000)

        # 如果响应拦截没拿到，尝试从页面 HTML 提取
        if not video_api_url:
            print("尝试从页面HTML提取视频URL...", flush=True)
            html = await page.content()
            # 尝试多种视频 URL 模式
            for pat in [
                r'/aweme/v1/playwm/\?[^"\'<>\s]+',
                r'/aweme/v1/play/\?[^"\'<>\s]+',
                r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*',
                r'https?://[^\s"\'<>]+/obj/[^\s"\'<>]+\.mp4[^\s"\'<>]*',
            ]:
                m = re.search(pat, html)
                if m:
                    raw = m.group(0)
                    if raw.startswith('/'):
                        video_api_url = 'https://www.douyin.com' + raw
                    else:
                        video_api_url = raw
                    # HTML 实体解码
                    import html as html_module
                    video_api_url = html_module.unescape(video_api_url)
                    print(f"HTML提取到: {video_api_url[:150]}", flush=True)
                    break

        # 尝试从 video 元素获取
        if not video_api_url:
            video_el = await page.query_selector('video')
            if video_el:
                src = await video_el.get_attribute('src')
                if src and 'http' in src and not src.startswith('blob:'):
                    video_api_url = src
                    print(f"VIDEO元素获取: {video_api_url[:150]}", flush=True)

        print(f"VIDEO_URL={video_api_url[:100] if video_api_url else 'NOT_FOUND'}", flush=True)

        # 获取标题
        title_el = await page.query_selector('h1')
        if title_el:
            video_title = await title_el.inner_text()
            video_title = sanitize_filename(video_title) or f"douyin_{video_id}"

        await browser.close()
        return video_api_url, video_title


async def _download_via_playwright(video_url, output_path_str, video_id):
    """通过 Playwright API 下载视频（保持浏览器上下文）"""
    from playwright.async_api import async_playwright

    _pw_browsers_path = Path(os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(Path.home() / "AppData" / "Local" / "ms-playwright")
    ))
    # 优先用轻量的 headless shell，启动更快
    _chromium_exe = _pw_browsers_path / "chromium_headless_shell-1208" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    if not _chromium_exe.exists():
        _chromium_exe = _pw_browsers_path / "chromium-1208" / "chrome-win64" / "chrome.exe"

    DESKTOP_UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            executable_path=str(_chromium_exe),
            args=[
                '--no-sandbox', '--disable-setuid-sandbox',
                '--disable-gpu', '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        context = await browser.new_context(
            user_agent=DESKTOP_UA,
            locale='zh-CN',
        )
        page = await context.new_page()
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        # 用 Playwright 的 fetch（浏览器上下文）请求视频 URL
        print(f"开始下载视频: {video_url[:100]}", flush=True)
        response = await context.request.fetch(video_url, headers={
            'User-Agent': DESKTOP_UA,
            'Referer': f'https://www.douyin.com/video/{video_id}',
        })

        body = await response.body()
        with open(output_path_str, 'wb') as f:
            f.write(body)
        print(f"下载完成，大小: {len(body)/1024/1024:.1f}MB", flush=True)
        await browser.close()


def process(video_url, output_dir_str):
    """下载抖音视频：先yt_dlp，失败则Playwright"""
    output_dir = Path(output_dir_str)
    pid = os.getpid()

    def push(event, data=""):
        msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        print(f"STATUS:{msg}", flush=True)

    def write_progress(pct):
        with open(str(output_dir / f"_dl_progress_{pid}.txt"), 'w', encoding='utf-8') as f:
            f.write(str(int(pct)))

    try:
        push("status", "正在下载抖音视频...")

        # 解析 video_id
        video_id = None
        if "douyin.com/video/" in video_url:
            m = re.search(r'douyin\.com/video/(\d+)', video_url)
            if m:
                video_id = m.group(1)
        elif "v.douyin.com" in video_url:
            # 短链接解析，支持重试（国内网络 v.douyin.com 可能失败）
            video_id = None
            for attempt in range(3):
                try:
                    req = urllib.request.Request(video_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    })
                    resp = urllib.request.urlopen(req, timeout=15)
                    final_url = resp.url
                    m = re.search(r'douyin\.com/video/(\d+)', final_url)
                    if m:
                        video_id = m.group(1)
                        break
                except Exception:
                    if attempt < 2:
                        time.sleep(2)
            if not video_id:
                return {"ok": False, "error": "短链接解析失败，已重试3次"}

        if not video_id:
            return {"ok": False, "error": "无法解析抖音视频ID"}

        # 方式1：yt_dlp
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

        ydl_opts = {
            'outtmpl': str(output_dir / "%(title)s.%(ext)s"),
            'format': 'bestvideo+bestaudio/best',
            'ffmpeg_location': str(Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                'Referer': 'https://www.douyin.com/',
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
            # 方式2：Playwright
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                write_progress(10)
                push("status", "[10%] 启动浏览器...")
                video_api_url, video_title = loop.run_until_complete(
                    _playwright_download(video_url, video_id, output_dir))
                loop.close()

                if not video_api_url:
                    return {"ok": False, "error": f"无法获取视频地址，视频ID={video_id}"}

                write_progress(60)
                push("status", "[60%] 获取到视频地址，下载中...")
                video_file = output_dir / f"{video_title}.mp4"

                loop2 = asyncio.new_event_loop()
                asyncio.set_event_loop(loop2)
                loop2.run_until_complete(_download_via_playwright(
                    video_api_url, str(video_file), video_id))
                loop2.close()

                write_progress(100)
                push("status", "[100%] Playwright下载完成")
            except Exception as e_pw:
                return {"ok": False, "error": f"抖音视频下载失败: {e_pw}"}

        if not video_file or not video_file.exists():
            return {"ok": False, "error": f"视频文件未找到: {video_title}"}

        file_size = video_file.stat().st_size
        if file_size < 50000:
            video_file.unlink()
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
    print(f"DY_DL_START pid={os.getpid()}", flush=True)
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
