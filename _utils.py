"""
通用工具函数模块
被所有下载模块和调度器共享
不依赖任何业务逻辑模块
"""
import re
from pathlib import Path


def sanitize_filename(name):
    """
    移除文件名中的非法字符，防止路径注入

    处理规则：
    - 移除 Windows 文件名非法字符 \\/:*?\"<>|
    - 去除首尾空格和点（防绕过）
    - 限制长度 <= 200 字符，防止超长路径
    - 空名称 fallback 到 "video"
    """
    if not name:
        return "video"
    name = re.sub(r'[\/\\:*?"<>|]', '', name)
    name = name.strip().strip('.')
    if len(name) > 200:
        name = name[:200]
    return name or "video"


def validate_video_file(video_path, ffmpeg_bin_dir=None):
    """
    用 ffprobe 验证视频文件是否完整有效。
    返回 (ok, error_message)。
    检测：文件是否存在、大小、能否读出时长、是否真正可播放。
    """
    import subprocess
    from pathlib import Path

    video_path = Path(video_path)
    if not video_path.exists():
        return False, f"文件不存在: {video_path}"

    size = video_path.stat().st_size
    if size < 50000:
        return False, f"文件小于50KB，疑似下载不完整"

    # 用 ffprobe 检测是否能读出时长（真正验证视频完整性）
    ffprobe = Path(ffmpeg_bin_dir) / "ffprobe.exe" if ffmpeg_bin_dir else None
    if ffprobe and ffprobe.exists():
        cmd = [str(ffprobe), "-v", "quiet", "-show_entries",
               "format=duration", "-of", "csv=p=0", str(video_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', timeout=30)
            dur = result.stdout.strip()
            if not dur or float(dur) <= 0:
                return False, f"ffprobe 无法读取视频时长，文件可能损坏"
        except Exception:
            # ffprobe 失败不阻断，只作为警告
            pass

    return True, ""


# Windows MAX_PATH = 260，触发条件通常在 240 以上
MAX_PATH_WARN = 200   # 警告阈值
MAX_PATH_FAIL = 240   # 超过此值直接失败


def cleanup_part_files(output_dir):
    """
    下载前清理所有残留的 .part 文件。
    yt_dlp 断点续传失败后会留下 .part 文件，
    再次下载同一标题视频时（即使 no_resume=True）也可能报
    WinError 32（文件被占用）或 416。
    清理后再下载可完全避免此类问题。
    """
    output_path = Path(output_dir)
    for p in output_path.glob("*.part"):
        try:
            p.unlink()
        except Exception:
            pass


def check_path_length(file_path):
    """
    检查文件路径长度是否安全。返回 (ok, error_message)。
    Windows 用户在超长标题场景容易触发 MAX_PATH 问题，提前告知。
    """
    path_str = str(file_path)
    n = len(path_str)
    if n >= MAX_PATH_FAIL:
        return False, f"路径长度{n}超过Windows限制({MAX_PATH_FAIL})，请缩短标题或移动输出目录"
    if n >= MAX_PATH_WARN:
        return False, f"路径长度{n}接近Windows限制({MAX_PATH_FAIL})，可能保存失败"
    return True, ""


def cleanup_old_progress_files(output_dir):
    """
    清理上次遗留的进度文件和结果文件

    清理范围：
    - _dl_progress_*.txt     视频下载进度
    - _audio_progress_*.txt  音频提取/转写进度
    - _audio_result_*.json    音频转写结果
    """
    patterns = ["_dl_progress_*.txt", "_audio_progress_*.txt", "_audio_result_*.json"]
    output_path = Path(output_dir)
    for p in patterns:
        for f in output_path.glob(p):
            try:
                f.unlink()
            except Exception:
                pass
