# B-Site 项目系统测试报告

| 项目 | 详情 |
|------|------|
| **项目名称** | B-Site (B站/抖音/小红书视频转文字) |
| **测试日期** | 2026-04-14 |
| **测试方法** | 代码审查 (Code Review) + 静态分析 (Static Analysis) |
| **测试范围** | 安全漏洞 / 系统稳定性 / 功能逻辑 |
| **综合评级** | **⚠️ 需要修复后上线** |

---

## 一、安全漏洞测试 (4项)

### 1.1 🔴 严重 — 路径遍历漏洞 (Path Traversal)

| 项目 | 详情 |
|------|------|
| **CWE 编号** | CWE-22: Path Traversal |
| **CVSS 3.1** | 8.1 (High) |
| **位置** | `b_site_launcher.py:473-484` — `/save` 端点 |
| **描述** | 用户可通过 POST 请求的 `file` 参数写入任意文件路径，服务器无任何路径校验 |

**问题代码**：
```python
@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    file_path = data.get("file", "")    # 用户完全控制路径
    content = data.get("content", "")    # 用户完全控制内容
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return json.dumps({"ok": True})
```

**攻击向量**：
```bash
curl -X POST http://TARGET:PORT/save \
  -H "Content-Type: application/json" \
  -d '{"file": "C:\\Windows\\System32\\config\\evil.exe", "content": "malicious_payload"}'
```

**修复建议**：
```python
from pathlib import Path

@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    file_path = data.get("file", "")
    content = data.get("content", "")

    safe_dir = OUTPUT_DIR.resolve()
    try:
        file_path = Path(file_path).resolve()
        if not str(file_path).startswith(str(safe_dir)):
            return jsonify({"ok": False, "error": "非法路径，只能保存到输出目录"}), 400
    except Exception:
        return jsonify({"ok": False, "error": "路径无效"}), 400

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({"ok": True})
```

**影响**：攻击者可覆盖系统文件、实现远程代码执行。

---

### 1.2 🔴 严重 — 无认证授权 (Missing Authentication)

| 项目 | 详情 |
|------|------|
| **CWE 编号** | CWE-306: Missing Authentication for Critical Function |
| **CVSS 3.1** | 8.0 (High) |
| **位置** | `b_site_launcher.py:559` |
| **描述** | Flask 服务绑定 `0.0.0.0` (所有网络接口)，无任何身份验证机制 |

**问题代码**：
```python
app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
```

**影响范围**：
- 同一局域网内的所有设备均可访问
- 任意用户可触发视频下载、转写
- 任意用户可通过 `/save` 覆盖任意文件（结合漏洞1.1）
- 任意用户可通过 `/restart` 重启服务（DoS）

**修复建议**（三选一）：

**方案A — 绑定本地回环（推荐用于本地使用）**：
```python
app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
```

**方案B — HTTP Basic Auth 装饰器**：
```python
from functools import wraps
import base64

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != 'admin' or auth.password != 'YOUR_STRONG_PASSWORD':
            return 'Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="B-Site"'}
        return f(*args, **kwargs)
    return decorated
```

**方案C — 绑定本地 + 启动时显示随机 Token**：
```python
import secrets
TOKEN = secrets.token_hex(16)

@app.route("/transcribe", methods=["GET"])
@require_token
def transcribe():
    ...
```

---

### 1.3 🟡 中等 — SSE 连接无限制 (Missing Resource Limits)

| 项目 | 详情 |
|------|------|
| **CWE 编号** | CWE-770: Allocation of Resources Without Limits |
| **CVSS 3.1** | 5.3 (Medium) |
| **位置** | `b_site_launcher.py:498-535` |

**问题描述**：无单IP连接数限制，攻击者可通过发起大量 SSE 连接耗尽服务器线程资源。

**修复建议**：
```python
from flask import request, jsonify
from collections import defaultdict
import time

# 连接计数器（生产环境建议用 Redis）
connection_counts = defaultdict(list)

def rate_limit_ip(max_connections=5, window=60):
    client_ip = request.remote_addr
    now = time.time()
    connection_counts[client_ip] = [
        t for t in connection_counts[client_ip] if now - t < window
    ]
    if len(connection_counts[client_ip]) >= max_connections:
        return False
    connection_counts[client_ip].append(now)
    return True

@app.route("/transcribe", methods=["GET"])
def transcribe():
    if not rate_limit_ip():
        return "连接数超限，请稍后再试", 429
    ...
```

---

### 1.4 🟡 中等 — URL 正则提取可被绕过 (Insufficient URL Validation)

| 项目 | 详情 |
|------|------|
| **CWE 编号** | CWE-20: Improper Input Validation |
| **CVSS 3.1** | 5.3 (Medium) |
| **位置** | `b_site_launcher.py:191-199` |

**问题代码**：
```python
url_pattern = r'https?://[a-zA-Z0-9._~%@:#=&?/,-]+'
matched = re.findall(url_pattern, raw_input)
for m in matched:
    url_lower = m.lower()
    if "bilibili.com" in url_lower:  # 简单字符串包含检查
        return video_url
```

**绕过示例**：
```
输入: "视频 https://www.bilibili.com.evil.com/video/BVxxx 请处理"
结果: 被错误识别为B站链接，实际指向恶意域名
```

**修复建议**：
```python
from urllib.parse import urlparse

ALLOWED_DOMAINS = {
    'bilibili.com', 'www.bilibili.com', 'm.bilibili.com', 'live.bilibili.com',
    'douyin.com', 'www.douyin.com', 'v.douyin.com',
    'xiaohongshu.com', 'www.xiaohongshu.com', 'xhslink.com',
}

def validate_video_url(url):
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    # 移除端口号
    host = netloc.split(':')[0]
    # 检查是否为允许的域名或子域名
    if host in ALLOWED_DOMAINS:
        return True
    # 检查是否为允许域名的子域名
    for allowed in ALLOWED_DOMAINS:
        if host.endswith('.' + allowed):
            return True
    return False
```

---

## 二、系统稳定性测试 (4项)

### 2.1 🟠 高 — 子进程 stdout 死锁风险 (Subprocess Deadlock)

| 项目 | 详情 |
|------|------|
| **位置** | `b_site_launcher.py:341-388` — `poll_subprocess()` 函数 |

**问题分析**：

`poll_subprocess` 线程中使用 `proc.stdout.readline()` 读取子进程输出，存在以下风险：

```
正常流程：
  子进程 stdout 写完 → readline() 返回 → 线程继续

异常流程（死锁）：
  子进程写入部分数据 → 子进程崩溃/被杀死
  → readline() 永远等待换行符 → 线程永远阻塞
  → proc.wait(timeout=3600) 触发 → proc.kill() 杀进程
  → 但 poll_thread 已在 readline() 中，无法终止
```

**代码片段**：
```python
def poll_subprocess():
    while not _poll_stop:
        try:
            raw = proc.stdout.readline()  # 🔴 可能永远阻塞
            if raw:
                line = raw.decode('utf-8', errors='replace').strip()
                ...
        except Exception:
            pass
        time.sleep(0.5)
```

**修复建议**（使用 `select` 实现非阻塞读取）：
```python
import select

def poll_subprocess():
    while not _poll_stop:
        # 使用 select 检测 stdout 是否可读，超时 0.5s
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            raw = proc.stdout.readline()
            if raw:
                line = raw.decode('utf-8', errors='replace').strip()
                # ... 处理逻辑
        if proc.poll() is not None:
            break
```

**注意**：`select.select` 在 Windows 上仅支持 socket，不支持 pipe。Windows 替代方案：
```python
import threading
import queue

def poll_subprocess():
    q = queue.Queue()
    def read_stdout():
        for line in iter(proc.stdout.readline, b''):
            q.put(line)
        q.put(None)  # 信号结束

    t = threading.Thread(target=read_stdout, daemon=True)
    t.start()

    while not _poll_stop:
        try:
            raw = q.get(timeout=0.5)
            if raw is None:
                break
            line = raw.decode('utf-8', errors='replace').strip()
            # ... 处理逻辑
        except queue.Empty:
            pass
        if proc.poll() is not None:
            break

    t.join(timeout=2)
```

---

### 2.2 🟡 中 — 裸 `except: pass` 吞掉关键错误

| 项目 | 详情 |
|------|------|
| **位置** | 多处 — `_audio_to_text.py`, `b_site_launcher.py` |
| **问题** | 所有进度文件写入失败被静默忽略，错误难以诊断 |

**出现位置**：
```python
# _audio_to_text.py:87-88
except:
    pass

# b_site_launcher.py:353-358
try:
    if audio_progress_file.exists():
        pct = int(audio_progress_file.read_text(encoding='utf-8').strip())
except:
    pass
```

**修复建议**：至少记录日志
```python
import logging
logger = logging.getLogger(__name__)

try:
    with open(progress_file, 'w', encoding='utf-8') as f:
        f.write(str(int(pct)))
except Exception as e:
    logger.warning(f"进度文件写入失败 [{progress_file}]: {e}")
```

---

### 2.3 🟡 中 — 临时文件清理存在竞态条件

| 项目 | 详情 |
|------|------|
| **位置** | `b_site_launcher.py:437-441`, `_audio_to_text.py:247-250` |
| **问题** | 系统崩溃时进度/结果文件无法清理，成为孤儿文件 |

**修复建议**：使用 `atexit` 注册清理函数
```python
import atexit

def cleanup():
    """清理所有临时进度文件"""
    for pattern in ["_dl_progress_*.txt", "_audio_progress_*.txt", "_audio_result_*.json"]:
        for f in OUTPUT_DIR.glob(pattern):
            try:
                f.unlink()
            except Exception:
                pass

atexit.register(cleanup)
```

---

### 2.4 🟢 低 — Whisper 模型内存累积

| 项目 | 详情 |
|------|------|
| **位置** | `_audio_to_text.py:158` |
| **问题** | 连续处理视频时 GPU 显存只增不减，长时间运行可能 OOM |

**分析**：每次调用 `process()` 都加载一次 `faster_whisper.WhisperModel`，模型不会自动卸载。

**修复建议**（单例模式）：
```python
_model_cache = None

def get_whisper_model():
    global _model_cache
    if _model_cache is None:
        _model_cache = faster_whisper.WhisperModel(
            WHISPER_MODEL, device="cuda", compute_type="float16"
        )
    return _model_cache
```

---

## 三、功能逻辑测试 (4项)

### 3.1 🔴 功能性 — f-string 缺失导致日志错误

| 项目 | 详情 |
|------|------|
| **位置** | `_dl_douyin.py:286` |
| **严重程度** | 功能性 Bug |

**问题代码**：
```python
push("status", "[100%] yt_dlp下载完成: {video_title}")
#                                                     ^^^^^^^^ 未插入变量！
```

**实际输出**：
```
[100%] yt_dlp下载完成: {video_title}   # 字面量，而非变量值
```

**修复**：添加 `f` 前缀
```python
push("status", f"[100%] yt_dlp下载完成: {video_title}")
```

---

### 3.2 🟠 功能性 — 抖音短链接解析无代理支持

| 项目 | 详情 |
|------|------|
| **位置** | `_dl_douyin.py:226-237` |
| **问题** | 国内网络环境下直接请求 `v.douyin.com` 很可能失败，无重试机制 |

**问题代码**：
```python
if "v.douyin.com" in video_url:
    try:
        req = urllib.request.Request(video_url, headers={...})
        resp = urllib.request.urlopen(req, timeout=10)
        # 无代理、无重试、网络异常直接失败
    except Exception as e:
        return {"ok": False, "error": f"短链接解析失败: {e}"}
```

**修复建议**：添加重试 + 超时
```python
import urllib.request
import time

def resolve_short_url(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            })
            resp = urllib.request.urlopen(req, timeout=15)
            return resp.url
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
    return None
```

---

### 3.3 🟡 代码 — JSON 响应不一致

| 项目 | 详情 |
|------|------|
| **位置** | 多处 |
| **问题** | 部分使用 `json.dumps()`，部分使用 `jsonify()`，HTTP 响应头不一致 |

**现状**：
```python
return json.dumps({"ok": True})                    # ✅ 正确但不一致
return json.dumps({"ok": False, "error": str(e)})  # ✅ 正确但不一致
```

**修复建议**：统一使用 `jsonify`
```python
from flask import jsonify

return jsonify({"ok": True})
return jsonify({"ok": False, "error": "错误信息"})
```

---

### 3.4 🟡 代码 — HTML 模板未分离

| 项目 | 详情 |
|------|------|
| **位置** | `b_site_launcher.py:23-169` (内嵌 HTML) |
| **问题** | 1) 难以维护 2) 无法缓存 3) 前后端无法独立开发 |

**修复建议**：使用 Flask 模板系统
```python
# b_site_launcher.py
from flask import render_template

@app.route("/")
def index():
    return render_template('index.html')
```

项目已有 `templates/index.html` 文件，但 Flask 启动器未使用。

---

## 四、测试总结

### 综合评级：⚠️ 需要修复后上线

| 维度 | 评级 | 说明 |
|------|------|------|
| **安全性** | 🔴 不合格 | 路径遍历 + 无认证，局域网内可远程代码执行 |
| **稳定性** | 🟠 基本可用 | 存在子进程死锁风险，需修复 |
| **功能正确性** | 🟠 有Bug | f-string 缺失导致日志错误 |
| **代码质量** | 🟡 一般 | 缺少日志、错误处理不规范、裸 except 滥用 |

### 阻塞上线问题（必须修复）

| 优先级 | 问题 | 位置 |
|--------|------|------|
| **P0** | 路径遍历漏洞 — `/save` 无路径校验 | `b_site_launcher.py:474` |
| **P0** | 无认证授权 — 服务暴露 | `b_site_launcher.py:559` |
| **P1** | f-string 缺失 — 日志输出错误 | `_dl_douyin.py:286` |

### 建议修复项（上线前修复）

| 优先级 | 问题 | 位置 |
|--------|------|------|
| **P2** | 子进程死锁风险 | `b_site_launcher.py:361` |
| **P2** | 裸 `except: pass` 滥用 | 多处 |
| **P3** | SSE 连接无限制 | `b_site_launcher.py:498` |
| **P3** | URL 正则验证不严格 | `b_site_launcher.py:191` |
| **P3** | JSON 响应不一致 | 多处 |
| **P4** | HTML 模板未分离 | `b_site_launcher.py:23` |
| **P4** | Whisper 模型内存累积 | `_audio_to_text.py:158` |

---

## 五、附录

### A. 测试环境

- **操作系统**: Windows 11 Enterprise (10.0.26200)
- **Python 版本**: 3.12
- **测试方法**: 静态代码审查（非动态渗透测试）
- **测试工具**: 手动代码审查

### B. 版本信息

项目当前版本：**v1.6.0** (2026-04-14)

### C. 建议的后续测试

1. **动态渗透测试** — 在隔离环境中实际发起路径遍历攻击
2. **压力测试** — 使用 `ab` 或 `wrk` 测试 SSE 连接限制
3. **模糊测试** — 对 `/save` 端点输入各种畸形数据
4. **长时稳定性测试** — 连续处理 10+ 个视频观察内存/GPU 占用

---

*报告生成时间: 2026-04-14*
*测试员: Claude Code (AI Automated Testing)*
