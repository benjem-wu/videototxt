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
