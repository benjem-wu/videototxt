# B-Site 视频转文字稿 · 版本变更记录

---

## v1.4.0

**日期：2026-04-14**

**主题：新增小宇宙播客下载支持**

### 新增功能

#### 1. 小宇宙播客下载模块 `_dl_xiaoyuzhoufm.py`

- 独立进程模块，接口与 B站/抖音/小红书 完全平行
- **检测方式**：`xiaoyuzhoufm.com` in URL
- **下载方式**：yt_dlp 直接下载（纯音频 m4a）
- **音频直链**：HTML `<meta property="og:audio">` 暴露了真实地址，yt-dlp 可直接识别
- 无需浏览器，纯网络请求即可完成

#### 2. 播客音频跳过 ffmpeg 提取步骤

- `_audio_to_text.py` 增加音频文件类型判断（.m4a/.mp3/.wav/.aac 等）
- 检测为纯音频文件时，跳过 ffmpeg 音频提取，直接进入 Whisper 转写
- 节省一次无意义的转码，提升播客处理效率

### 改进

#### 1. 重置按钮行为修复

- `resetAll()` 改为调用 `/restart` 重启服务 + `location.reload(true)` 强制刷新
- 解决之前只清前端状态、不重启服务导致的缓存问题

#### 2. Web 标题/提示语更新

- 标题：`"B站/抖音/小红书/小宇宙视频转文字稿"`
- input placeholder：`"请输入B站、抖音、小红书或小宇宙链接"`

---

## v1.2.1
**日期：2026-04-14**
**主题：修复416/WinError32、根治.part残留文件**

### Bug 修复

#### 1. [P0] B站下载 HTTP 416 错误
- **问题**：上次下载残留的 `.mp4.part` 文件导致 yt_dlp 断点续传失败，B站服务器返回 416 Requested Range Not Satisfiable
- **修复**：
  - 所有下载器（B站/抖音/小红书）统一补加 `no_resume: True`
  - 新增 `cleanup_part_files()` 在每次下载前清理所有残留 `.part` 文件

#### 2. [P0] 小红书下载 WinError 32
- **问题**：`.mp4.part` 文件被 yt_dlp 进程锁定无法 rename，Windows 返回 "另一个程序正在使用此文件"，yt_dlp 重试 3 次后放弃
- **修复**：同上的 `no_resume: True` + `cleanup_part_files()` 从源头避免

---

## v1.2.0
**日期：2026-04-14**
**主题：四项重要改进**

### 新增功能

#### 1. 视频文件完整性校验
- **位置**：新增 `validate_video_file()` 在 `_utils.py`
- **机制**：用 ffprobe 检测视频实际时长，假文件/ corrupt 文件在进入转写前就被拦截
- **应用**：B站/抖音/小红书三个下载器下载完成后统一校验

#### 2. CUDA OOM 自动降级
- **位置**：`_audio_to_text.py`
- **机制**：Whisper 模型加载时优先使用 `float16`，失败后自动切换 `int8`，GPU 显存不足时不再崩溃
- **流程**：`float16` → 失败则尝试 `int8` → 仍失败则上抛异常

#### 3. B站下载网络重试
- **位置**：`_dl_bilibili.py`
- **机制**：Cookie 方式最多重试 3 次（每次间隔 2 秒），网络抖动自动恢复
- **fallback**：Cookie 3 次全失败后自动切换无 Cookie 方式

#### 4. Windows MAX_PATH 路径长度保护
- **位置**：新增 `check_path_length()` 在 `_utils.py`
- **机制**：保存文字稿前检查路径长度，超过 200 字符警告，超过 240 字符直接失败并提示
- **自动修复**：路径过长时自动截断标题至 80 字符重试

### 代码变更

| 文件 | 变更 |
|------|------|
| `_utils.py` | 新增 `validate_video_file()`（ffprobe 时长检测）、`check_path_length()`（路径长度检查） |
| `_audio_to_text.py` | 模型加载增加 float16→int8 降级逻辑、保存前路径长度检查 |
| `_dl_bilibili.py` | Cookie 方式重试循环、ffprobe 完整性校验 |
| `_dl_douyin.py` | ffprobe 完整性校验 |
| `_dl_xiaohongshu.py` | ffprobe 完整性校验 |

---

## v1.1.0
**日期：2026-04-14**
**主题：修复B站下载416错误 + 多个鲁棒性改进**

### Bug 修复

#### 1. [P0] B站下载 HTTP 416 错误
- **根因**：yt_dlp 默认尝试断点续传，但 B站 服务器不支持
- **修复**：在 yt_dlp 选项中加入 `no_resume: True`，强制从 0 开始下载

#### 2. [P1] download_hook 输出混入 yt_dlp stderr
- **根因**：download_hook 内调用 `push()` 写 STATUS 到 stdout，导致和 yt_dlp stderr 混在一起
- **表现**：日志里出现 `ERROR: ...STATUS:{"event":...` 这种混杂输出
- **修复**：download_hook 不再写 STATUS，只写进度文件（整数百分比）

### 改进

#### 1. 抖音短链接解析重试
- **位置**：`_dl_douyin.py`
- **机制**：`v.douyin.com` 短链接解析失败时最多重试 3 次，每次间隔 2 秒
- **解决**：国内网络访问短链接不稳定的问题

#### 2. 代码质量规范化
- **位置**：所有模块
- **修复**：
  - 修复裸 `except:` → `except Exception:`
  - 删除 `_dl_bilibili.py` 中重复的 `from pathlib import Path` 导入

#### 3. Web 标题更新
- `"B站/抖音视频转文字稿"` → `"B站/抖音/小红书视频转文字稿"`
- input placeholder 更新为 `"请输入B站、抖音或小红书视频链接"`

### 代码变更

| 文件 | 变更 |
|------|------|
| `_dl_bilibili.py` | `no_resume: True`、download_hook 只写文件不写 STATUS |
| `_dl_douyin.py` | 短链接解析 3 次重试、修复裸 except |
| `b_site_launcher.py` | `/transcribe` 错误返回改用 `jsonify()` |
| `templates/index.html` | 标题/提示语加小红书 |

---

## v1.7.0
**日期：2026-04-14**
**主题：安全修复 + 代码质量改进**

### 安全修复

#### 1. [P0] 路径遍历漏洞修复
- **位置**：`/save` 端点
- **问题**：用户可通过 POST 请求的 `file` 参数写入任意文件路径，无任何校验
- **修复**：增加路径边界校验，目标路径必须在 `OUTPUT_DIR` 目录内，否则返回 400 错误

#### 2. [P0] 无认证授权修复
- **位置**：`app.run(host="0.0.0.0")`
- **问题**：Flask 服务绑定所有网络接口，同一局域网内任意设备可访问并操作
- **修复**：改为 `host="127.0.0.1"`，只允许本机访问

### 代码质量改进

#### 1. [P1] f-string 字面量 Bug 修复
- **位置**：`_dl_douyin.py:286`
- **问题**：`push("status", "[100%] yt_dlp下载完成: {video_title}")` 缺少 `f` 前缀
- **修复**：改为 `push("status", f"[100%] yt_dlp下载完成: {video_title}")`

#### 2. [P2] 裸 `except: pass` 规范化
- **位置**：`b_site_launcher.py`（5处）、`_audio_to_text.py`（6处）
- **问题**：所有进度文件写入失败被静默忽略，错误难以诊断
- **修复**：统一改为 `except Exception:`，保持代码一致性

#### 3. [P4] HTML 模板外置
- **位置**：`b_site_launcher.py`
- **问题**：HTML 代码内嵌在 Python 文件中，难以维护
- **修复**：使用 Flask `render_template()` 渲染 `templates/index.html`，删除内嵌 HTML

#### 4. [P4] Whisper 模型单例缓存
- **位置**：`_audio_to_text.py`
- **问题**：连续处理视频时 GPU 显存只增不减，长时间运行可能 OOM
- **修复**：新增 `_whisper_model_cache` 全局变量，模型加载一次后缓存复用

---

## v1.6.0
**日期：2026-04-14**
**主题：鲁棒性改进（子进程清理 + 文件名安全 + 进度文件自清理）**

### 新增功能

#### 1. 子进程超时强制终止
- `dl_proc.wait(timeout=600)` 超时后显式调用 `dl_proc.kill()` + `dl_proc.wait()`
- 防止子进程在超时后继续空转消耗资源

#### 2. 启动时清理历史进度文件
- `cleanup_old_progress_files(OUTPUT_DIR)` 在服务启动时执行
- 清理 `F:\outfile\` 下残留的 `_dl_progress_*.txt`、`_audio_progress_*.txt`、`_audio_result_*.json`

#### 3. 统一文件名安全函数 `sanitize_filename()`
- 新增 `sanitize_filename(name)` 工具函数
- 移除 `\/:*?"<>|` 等非法字符
- 截断超长标题（>200字符）
- 应用于：B站/抖音/小红书三个下载模块的 Playwright 兜底路径

### Bug 修复

#### 1. `b_site_launcher.py` 重复代码
- **根因**：上次插入分隔线逻辑时，重复复制了一段代码
- **表现**：下载成功后 `[100%] 视频下载完成` 日志出现两次
- **修复**：删除重复的 `if not ok` 检查和 `video_file`/`video_title` 赋值

---

## v1.5.0
**日期：2026-04-13**
**主题：新增小红书视频下载支持 + 全链路分隔线完善**

### 新增功能

#### 1. 小红书视频下载模块 `_dl_xiaohongshu.py`
- 独立进程模块，接口与 B站/抖音 完全平行
- **检测方式**：`xiaohongshu.com` in URL
- **下载方式**：**yt_dlp 优先** + Playwright 浏览器兜底（和抖音一致）
  - yt_dlp 失败后才走 Playwright（`chrome-headless-shell.exe`）
  - 进度节点：`[1%]` yt_dlp尝试 → `[10%]` Playwright启动 → `[60%]` 获取直链 → `[100%]` 下载完成
- **视频提取**（Playwright 方式）：
  - 拦截含视频的 API 响应
  - HTML 多模式正则（`.mp4`、`sns-video`、`byteimg`、`lsy.xiaohongshu.com`）
  - `<video>` 元素 `src` 属性
- **标题提取**：优先从 `h1`、`.title`、`[data-v-title]`、`.note-content .title` 获取

#### 2. 阶段分隔线完善
全流程三个分隔节点：
- `─── 视频下载完成 ✓ ───`
- `─── 音频提取完成 ✓ ───`（新增，ffmpeg 提取完成、Whisper 模型加载前）
- `─── 音频转文字完成 ✓ ───`

#### 3. Web 标题更新
- `"B站/抖音视频转文字稿"` → `"B站/抖音/小红书视频转文字稿"`

### Bug 修复

#### 1. URL 检测遗漏小红书
- **根因**：`parse_video_url()` 只匹配 `bilibili.com` 和 `douyin.com`，不识别 `xiaohongshu.com`
- **修复**：正则条件加入 `xiaohongshu.com`

#### 2. `_extract_video_from_page` 未加 `await`
- **根因**：async 函数直接当同步调用，报错 `unknown url type: 'coroutine object _extract_video_from_page'`
- **修复**：调用处加 `await`

#### 3. 小红书 URL 正则不匹配 `/discovery/item/` 路径
- **根因**：正则只匹配 `/explore/` 路径，实际链接为 `/discovery/item/`
- **修复**：`r'xiaohongshu\.com/(?:explore|discovery/item)/([a-zA-Z0-9]+)'`

### 代码变更

| 文件 | 变更 |
|------|------|
| `b_site_launcher.py` | ① 文件头注释加入 `_dl_xiaohongshu.py` ② 新增 `is_xiaohongshu` 检测 ③ script_name 选择逻辑加入小红书分支 ④ Web 标题加"小红书" ⑤ `parse_video_url()` 加入小红书支持 |
| `_dl_xiaohongshu.py` | 重写为 yt_dlp优先 + Playwright兜底策略，含 await 修复和 URL 正则修复 |
| `_audio_to_text.py` | 音频提取完成后加 `─── 音频提取完成 ✓ ───` 分隔线 |

---

## v1.4.0
**日期：2026-04-13**
**主题：进度显示系统 + 抖音下载稳定性修复 + 结果文件泄漏修复**

### 新增功能

#### 1. 全链路百分比进度显示
- **视频下载**：yt_dlp 的 `progress_hooks` 实时推送下载百分比，写入 `_dl_progress_{pid}.txt`
- **音频提取**：`ffprobe` 先获取总时长 → `ffmpeg -progress pipe:1` 实时解析 `out_time_ms=` 行推算百分比
- **音频转写**：Whisper 转写时按音频位置映射 5%~95%，每秒推送一次 ETA

进度文件路径：
```
F:\outfile\_dl_progress_{pid}.txt       （视频下载进度，0~100整数）
F:\outfile\_audio_progress_{pid}.txt    （音频提取+转写进度，0~100整数）
```

#### 2. 阶段分隔线
- 下载完成：`─── 视频下载完成 ✓ ───`
- 转写完成：`─── 音频转文字完成 ✓ ───`
- 前端自动识别以 `───` 开头的消息，渲染为居中灰色分隔行

#### 3. 抖音下载超时延长
- `b_site_launcher.py` 中 `dl_proc.wait(timeout=600)`（原 300 秒）

### Bug 修复

#### 1. "转写器无输出" Bug（核心根因）
- **现象**：文字稿实际生成成功，但网页报错"转写器无输出"
- **根因**：
  - `proc.stdout.readline()` 在 Windows 返回 **bytes**，但代码用 `str` 方法操作
  - `line.startswith('STATUS:')` 中 `'STATUS:'` 是 str，bytes 无法匹配，导致所有 STATUS/RESULT 行全部跳过
- **修复**：`raw.decode('utf-8', errors='replace')` 后再操作（2处：poll 线程内 + wait 后的备用读取）

#### 2. `ImportError: cannot access local variable 'threading'` 编译错误
- **根因**：`import threading` 被放在 Step 2 的 try 块内，但 `threading.Thread()` 在 finally 块后调用，Python 把 threading 当作函数局部变量
- **修复**：移除重复的 `import threading`，使用文件顶部全局导入

#### 3. `_audio_result_{pid}.json` 文件泄漏
- **根因**：JSON 文件读取放在 `if not txt_result and result_file.exists()` 内，读取失败时 `unlink()` 不执行
- **修复**：读取无论成功失败都在 `finally` 块外执行 `unlink()`

#### 4. 抖音 Playwright 超时卡死（300秒）
- **根因**：
  1. 优先用完整 `chrome.exe`，启动极慢（需编译 shader）
  2. `--headless=new` 对 headless shell 冗余
  3. 有两个重复的 `handle_response` 定义，后者覆盖前者
  4. 总超时仅 300 秒，浏览器方式不够用
- **修复**：
  1. 优先用 `chrome-headless-shell.exe`（轻量很多）
  2. 去掉冗余参数：`--headless=new`、`--disable-software-rasterizer`、`--disable-features=WinNativeControls`
  3. 合并重复的 `handle_response` 和 `add_init_script`
  4. 浏览器等待从 5+5 秒减为 3+3 秒
  5. 超时延长到 600 秒
  6. `video_id=None` 时直接用原始短链接导航（不再访问 `.../video/None`）
  7. `page.goto` 加 try/except 保护

### 代码变更

| 文件 | 变更 |
|------|------|
| `b_site_launcher.py` | ① Step 1 改用 `Popen` + 轮询线程 ② stdout bytes 解码 ③ 读结果顺序改为 `_stdout_lines` → result file → direct stdout ④ SSE timeout 7200s ⑤ 清理逻辑完善 ⑥ 加分隔线 |
| `_audio_to_text.py` | ① 加 `write_progress()` 写进度文件 ② ffprobe 获取总时长 ③ ffmpeg `-progress pipe:1` 实时解析 ④ 转写进度 5%~95% 映射 ⑤ 清理音频文件和进度文件 |
| `_dl_bilibili.py` | ① 加 `progress_hooks` 写下载进度 ② `write_progress()` 写进度文件 |
| `_dl_douyin.py` | ① 优先 chrome-headless-shell ② 清理冗余参数和重复定义 ③ 缩短等待时间 ④ 加短链接 fallback 导航 ⑤ 超时 600s |

---

## v1.3.2
**日期：2026-04-14**
**主题：增强文件清理策略（自动删除非 TXT 残留文件）**

### Bug 修复

#### 1. [P1] JSON 残留文件未清理
- **问题**：转写完成后，output_dir 下会残留 `_audio_result_{pid}.json` 等临时文件
- **根因**：之前的清理逻辑只针对 mp4/mkv/audio.wav 等特定扩展名，未覆盖 json 文件
- **修复**：在清理流程末尾增加兜底逻辑，删除所有非 `.txt` 文件，确保目录只保留最终文字稿

---

## v1.3.1

**日期：2026-04-14**

**主题：下载器 stdout 重构（实时 STATUS 推送）**

### 改进

#### 1. 下载进度实时推送
- **位置**：`b_site_launcher.py` Step 1
- **旧逻辑**：子进程只写进度文件，父进程轮询文件（最多1秒延迟）
- **新逻辑**：新增 `read_stdout()` 线程，每收到 `STATUS:` 行立即推送；收到 `RESULT:` 行或进程退出时停止
- **效果**：下载进度推送几乎零延迟

#### 2. 错误处理改进
- `push()` 增加 `None` 检查，避免 `json.dumps(None)` 报错
- `PYTHONUNBUFFERED=1` 确保子进程 stdout 无缓冲
- stderr 重定向到 `DEVNULL`，避免 yt_dlp stderr 混入

---

## v1.3.0
**日期：2026-04-13**
**主题：独立进程重构（yt_dlp + Playwright 分离）**

### 重大架构变更

将原来的单体下载模块拆分为独立子进程：
- `_dl_bilibili.py`：B站视频下载（yt_dlp，优先 Chrome Cookie 方式）
- `_dl_douyin.py`：抖音视频下载（yt_dlp 优先，Playwright 浏览器兜底）
- `_audio_to_text.py`：音频提取 + Whisper 转写
- `b_site_launcher.py`：调度器，通过 subprocess 启动以上模块

### 关键机制

- **双通道进度**：子进程同时向 stdout 写 `STATUS:` 行 + 向进度文件写整数百分比
- **结果文件传递**：`_audio_result_{pid}.json` 作为可靠的结果载体（绕过 stdout pipe 编码问题）
- **SSE 长连接**：7200 秒（2小时）超时，支持漫长转写

---

## v1.2.0
**日期：2026-04-13**
**主题：Web UI 重构 + PaddleOCR 集成**

- 全新深色主题 Web UI
- `/save` 接口支持保存文字稿到本地
- `/restart` 接口支持热重启服务
- 集成 PaddleOCR 作为图片文字识别模块（`F:\CODE\paddle_ocr_agent.py`）

---

## v1.1.0
**日期：2026-04-13**
**主题：基础下载 + 转写流程**

- B站视频下载（BilibiliVideoDownloader）
- 抖音视频下载（DouyinVideoDownloader）
- 音频提取（ffmpeg）
- Whisper 转写（faster-whisper，large-v3 模型）
- Flask Web UI（SSE 实时推送）

---

## 版本号规则

```
v{主版本}.{次版本}.{修订号}
主版本：重大架构变更（如独立进程拆分）
次版本：新功能（如进度显示系统）
修订号：Bug 修复、细节优化
```

---

## 待办 / 已知问题

- [x] `_douyin_dl.py`（旧版独立进程脚本）已删除（v1.6.0）
- [ ] 抖音 Playwright 方式在部分网络环境下仍可能超时，可考虑加入重试机制
- [x] 进度文件清理：服务启动时自动清理历史进度文件（v1.6.0）
