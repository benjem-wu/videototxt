# B-Site

B站 / 抖音 / 小红书视频转文字稿工具。

## 功能

- **多平台支持**：B站、抖音、小红书视频链接自动识别与下载
- **双通道下载**：yt_dlp 优先 + Playwright 浏览器兜底
- **实时进度**：SSE 实时推送下载 / 转写进度
- **文字稿保存**：Web 界面一键保存转写结果

## 环境要求

- Python 3.10+
- ffmpeg（已包含在 `ffmpeg/` 目录）
- faster-whisper（large-v3 模型）
- Playwright（浏览器备用方式）

## 安装依赖

```bash
pip install flask faster-whisper yt-dlp playwright
playwright install chromium
```

## 使用方法

1. 运行 `启动.bat` 或直接运行：
   ```bash
   python b_site_launcher.py
   ```
2. 浏览器打开 `http://127.0.0.1:{port}`（启动时显示端口号）
3. 粘贴视频链接，点击开始

## 项目结构

```
b_site/
├── b_site_launcher.py     # Flask Web 服务 + 调度器
├── _dl_bilibili.py       # B站视频下载（独立进程）
├── _dl_douyin.py         # 抖音视频下载（独立进程）
├── _dl_xiaohongshu.py    # 小红书视频下载（独立进程）
├── _audio_to_text.py     # 音频提取 + Whisper 转写
├── _utils.py             # 通用工具函数
├── templates/index.html  # Web 前端模板
├── ffmpeg/               # ffmpeg 二进制文件
└── CHANGELOG.md          # 版本变更记录
```

## 版本

- v1.7.0 - 安全修复 + 代码质量改进
- v1.6.0 - 鲁棒性改进
- v1.5.0 - 小红书视频下载支持