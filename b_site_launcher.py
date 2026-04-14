"""
B站/抖音视频转文字稿 - 调度器
双击运行，自动启动服务并打开浏览器
拆分后结构：
  _dl_bilibili.py      - B站视频下载
  _dl_douyin.py       - 抖音视频下载
  _dl_xiaohongshu.py  - 小红书视频下载
  _audio_to_text.py - 音频转文字（共用）
"""
import os
import sys
import threading
import time
import socket
import queue
import json
import subprocess
import webbrowser
import re
import atexit
from pathlib import Path


# ==================== 内嵌 HTML ====================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>B站/抖音/小红书视频转文字稿</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"Microsoft YaHei","PingFang SC",sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:40px 20px}
h1{font-size:24px;font-weight:600;margin-bottom:30px;color:#fff;letter-spacing:2px}
.container{width:100%;max-width:900px;display:flex;flex-direction:column;gap:20px}
.input-box{display:flex;gap:10px}
input[type=text]{flex:1;padding:14px 18px;border-radius:10px;border:1px solid #333;background:#16213e;color:#e0e0e0;font-size:15px;outline:none;transition:border-color .2s}
input[type=text]:focus{border-color:#0f9467}
input[type=text]::placeholder{color:#666}
button{padding:14px 30px;border-radius:10px;border:none;background:#0f9467;color:#fff;font-size:15px;font-weight:600;cursor:pointer;transition:background .2s,transform .1s;white-space:nowrap}
button:hover{background:#0d8058}
button:active{transform:scale(.97)}
button:disabled{background:#333;color:#777;cursor:not-allowed;transform:none}
#resetBtn{background:#444}
#resetBtn:hover{background:#555}
.output-box{background:#16213e;border-radius:12px;border:1px solid #333;padding:20px;min-height:200px;max-height:300px;overflow-y:auto;font-size:15px;line-height:1.8}
.text-result{background:#0f1929;border-radius:12px;border:1px solid #333;padding:20px;min-height:300px;max-height:500px;overflow-y:auto;font-size:15px;line-height:2;white-space:pre-wrap;word-break:break-all;color:#e0e0e0;outline:none}
.text-result::-webkit-scrollbar{width:6px}
.text-result::-webkit-scrollbar-track{background:#0f1929}
.text-result::-webkit-scrollbar-thumb{background:#444;border-radius:3px}
.text-result:focus{border-color:#0f9467}
#saveBtn{background:#333;color:#777;cursor:not-allowed}
#saveBtn.active{background:#0f9467;color:#fff;cursor:pointer}
#saveBtn.active:hover{background:#0d8058}
.save-row{display:flex;justify-content:flex-end;margin-top:8px}
.output-box::-webkit-scrollbar{width:6px}
.output-box::-webkit-scrollbar-track{background:#16213e}
.output-box::-webkit-scrollbar-thumb{background:#444;border-radius:3px}
.placeholder{color:#555;text-align:center;margin-top:160px}
.log-line{color:#aaa;margin-bottom:4px}
.log-line .tag{color:#0f9467;font-weight:600}
.log-line .err{color:#e74c3c}
.log-line .done{color:#f39c12}
.log-line .info{color:#888;font-style:italic}
.footer{margin-top:30px;font-size:12px;color:#444;text-align:center}
</style>
</head>
<body>
<h1>B站/抖音视频转文字稿</h1>
<div class=container>
<div class=input-box>
<input type=text id=urlInput placeholder="请输入B站或抖音视频链接" onkeydown="if(event.key==='Enter')startTranscribe()">
<button id=startBtn onclick=startTranscribe()>转成文字</button>
<button id=resetBtn onclick=resetAll()>重置</button>
</div>
<div class=output-box id=output><div class=placeholder>转写进度将显示在这里...</div></div>
<div class=text-result id=textResult style=display:none contenteditable=true spellcheck=false oninput=onTextChange()></div>
<div class=save-row id=saveRow style=display:none><button id=saveBtn onclick=saveText()>保存</button></div>
</div>
<div class=footer>Faster-Whisper Large-v3 GPU加速 · 请确保CUDA环境已就绪</div>
<script>
let es=null,originalContent='',currentFilePath='',isRunning=false;
function startTranscribe(){
  if(isRunning)return;
  const url=document.getElementById('urlInput').value.trim();
  if(!url){alert('请输入B站或抖音视频链接');return}
  isRunning=true;
  const output=document.getElementById('output');
  const textResult=document.getElementById('textResult');
  const btn=document.getElementById('startBtn');
  output.innerHTML='';
  textResult.style.display='none';
  textResult.textContent='';
  originalContent='';currentFilePath='';
  document.getElementById('saveRow').style.display='none';
  document.getElementById('saveBtn').classList.remove('active');
  btn.disabled=true;btn.textContent='转写中...';
  addLog('开始处理: '+url);
  es=new EventSource('/transcribe?url='+encodeURIComponent(url));
  es.addEventListener('status',function(e){addLog(e.data,'tag')});
  es.addEventListener('done',function(e){
    const result=JSON.parse(e.data);
    addLog('✅ 全部完成！文件: '+result.file,'done');
    textResult.style.display='block';
    textResult.textContent=result.content;
    originalContent=result.content;currentFilePath=result.file;
    document.getElementById('saveRow').style.display='flex';
    document.getElementById('saveBtn').classList.remove('active');
    btn.disabled=false;btn.textContent='转成文字';es.close();es=null;isRunning=false
  });
  es.addEventListener('error',function(e){
    addLog('❌ 连接错误: '+(e.data||'无法连接服务器'),'err');
    btn.disabled=false;btn.textContent='转成文字';es.close();es=null;isRunning=false
  });
  es.onerror=function(){
    addLog('⚠️ 连接中断','err');
    btn.disabled=false;btn.textContent='转成文字';
    if(es)es.close();es=null;isRunning=false
  };
}
function addLog(text,type){
  const output=document.getElementById('output');
  const p=document.createElement('div');p.className='log-line';
  // 分隔线
  if(text.startsWith('───')){
    p.innerHTML='<span class=divider>'+text+'</span>';
    p.style.textAlign='center';
    p.style.color='#666';
    p.style.fontSize='13px';
    p.style.margin='4px 0';
  } else if(type==='tag'){
    p.innerHTML='<span class=tag>▶</span> '+text;
  } else if(type==='done'){
    p.innerHTML='<span class=done>'+text+'</span>';
  } else if(type==='err'){
    p.innerHTML='<span class=err>'+text+'</span>';
  } else {
    p.textContent=text;
  }
  output.appendChild(p);output.scrollTop=output.scrollHeight
}
function resetAll(){
  if(es){es.close();es=null}
  fetch('/restart',{method:'POST'}).finally(()=>{
    window.location.reload(true);
  });
}
function onTextChange(){
  const textResult=document.getElementById('textResult');
  const saveBtn=document.getElementById('saveBtn');
  if(textResult.textContent!==originalContent)saveBtn.classList.add('active');
  else saveBtn.classList.remove('active')
}
function saveText(){
  const textResult=document.getElementById('textResult');
  const content=textResult.textContent;
  if(content===originalContent)return;
  const btn=document.getElementById('saveBtn');
  btn.textContent='保存中...';btn.classList.remove('active');
  fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:currentFilePath,content:content})})
  .then(r=>r.json()).then(data=>{
    if(data.ok){
      originalContent=content;btn.textContent='已保存';
      setTimeout(()=>{btn.textContent='保存';btn.classList.remove('active')},1500)
    }else{btn.textContent='保存失败';setTimeout(()=>btn.textContent='保存',2000)}
  }).catch(()=>{btn.textContent='保存失败';setTimeout(()=>btn.textContent='保存',2000)})
}
</script>
</body>
</html>"""


# ==================== 路径兼容（dev / exe 通用）===================
def _get_exe_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


# ==================== 配置 ====================
BASE_DIR = _get_exe_dir()
OUTPUT_DIR = Path(r"F:\outfile")

task_queue = queue.Queue()


# ==================== 共用工具函数 ====================
from _utils import sanitize_filename, cleanup_old_progress_files


# ==================== URL domain whitelist ====================
ALLOWED_DOMAINS = {
    'bilibili.com', 'www.bilibili.com', 'm.bilibili.com', 'live.bilibili.com',
    'douyin.com', 'www.douyin.com', 'v.douyin.com',
    'xiaohongshu.com', 'www.xiaohongshu.com', 'xhslink.com',
}

def is_allowed_video_url(url):
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(':')[0]
        if host in ALLOWED_DOMAINS:
            return True
        for domain in ALLOWED_DOMAINS:
            if host.endswith('.' + domain):
                return True
        return False
    except Exception:
        return False

def parse_video_url(raw_input):
    url_pattern = r'https?://[a-zA-Z0-9._~%@:#=&?/,-]+'
    matched = re.findall(url_pattern, raw_input)
    for m in matched:
        url = m.rstrip(r'.,;:!?)ﾞﾞ').rstrip('/')
        if is_allowed_video_url(url):
            return url
    return None


def run_subprocess(script_name, args, timeout=180):
    """运行独立进程脚本，返回 (ok, result_dict, stderr_preview)"""
    python_exe = sys.executable
    script_path = BASE_DIR / script_name

    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONIOENCODING': 'utf-8'}
    proc = subprocess.run(
        [python_exe, str(script_path)] + args,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=timeout,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        env=env
    )

    # 解析 RESULT: 行
    result = None
    if proc.stdout:
        for line in proc.stdout.split('\n'):
            if line.startswith('RESULT:'):
                try:
                    result = json.loads(line[7:])
                except json.JSONDecodeError:
                    pass
                break

    stderr_preview = proc.stderr[:500] if proc.stderr else ''
    return proc.returncode == 0, result, stderr_preview


# ==================== 核心处理函数（在线程中运行）===================
def yield_output(q, video_url, output_dir):
    """后台线程：下载视频 → 转写 → 推送进度到队列"""
    VIDEO_URL = video_url
    is_douyin = "douyin.com" in video_url
    is_xiaohongshu = "xiaohongshu.com" in video_url

    def push(event, data=""):
        q.put(json.dumps({"event": event, "data": data}, ensure_ascii=False))

    import subprocess as sub_mod

    try:
        # ---- Step 1：下载视频 ----
        push("status", "[0%] 正在下载视频...")

        if is_xiaohongshu:
            script_name = "_dl_xiaohongshu.py"
        elif is_douyin:
            script_name = "_dl_douyin.py"
        else:
            script_name = "_dl_bilibili.py"
        push("status", f"[0%] 启动{script_name}...")
        python_exe = sys.executable
        script_path = BASE_DIR / script_name
        env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONIOENCODING': 'utf-8'}
        dl_proc = sub_mod.Popen(
            [python_exe, str(script_path), video_url, str(output_dir)],
            stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
            creationflags=getattr(sub_mod, 'CREATE_NO_WINDOW', 0),
            env=env
        )
        dl_pid = dl_proc.pid
        dl_progress_file = output_dir / f"_dl_progress_{dl_pid}.txt"

        # 后台轮询进度文件和子进程状态
        def poll_dl():
            last_pct = 0
            last_pct_time = time.time()
            while True:
                if dl_proc.poll() is not None:
                    break
                if dl_progress_file.exists():
                    try:
                        pct = int(dl_progress_file.read_text(encoding='utf-8').strip())
                        if pct != last_pct and pct > last_pct:
                            last_pct = pct
                            last_pct_time = time.time()
                        elif pct == last_pct and last_pct > 0:
                            # 进度停滞超过120秒，说明可能卡在合并阶段，强制终止
                            if time.time() - last_pct_time > 60:
                                print(f"[poll_dl] 进度停滞{pct}%超过120秒，强制终止", flush=True)
                                dl_proc.kill()
                                break
                    except Exception:
                        pass
                time.sleep(1)

        poll_thread = threading.Thread(target=poll_dl, daemon=True)
        poll_thread.start()

        try:
            dl_proc.wait(timeout=600)
        except sub_mod.TimeoutExpired:
            dl_proc.kill()
            dl_proc.wait()
            push("error", "视频下载超时（超过10分钟），已强制终止")
            return
        finally:
            poll_thread.join(timeout=2)

        stderr = dl_proc.stderr.read().decode('utf-8', errors='replace')[:500]
        if stderr:
            push("status", f"下载器stderr前200字: {stderr[:200]}")

        # 读取结果
        dl_result = None
        stdout_text = dl_proc.stdout.read().decode('utf-8', errors='replace')
        for line in stdout_text.split('\n'):
            if line.startswith('RESULT:'):
                try:
                    dl_result = json.loads(line[7:])
                except json.JSONDecodeError:
                    pass
                break

        # 清理进度文件
        try:
            dl_progress_file.unlink()
        except Exception:
            pass

        ok = dl_proc.returncode == 0 and dl_result and dl_result.get('ok')
        if not ok:
            err = dl_result.get('error', '未知错误') if dl_result else '下载器无输出'
            push("error", f"视频下载失败: {err}")
            return

        video_file = Path(dl_result['file'])
        video_title = dl_result['title']
        push("status", f"[100%] 视频下载完成: {video_title}")
        push("status", "─── 视频下载完成 ✓ ───")

        # ---- Step 2：音频转文字 ----
        push("status", "[0%] 启动音频转文字模块...")
        python_exe = sys.executable
        script_path = BASE_DIR / "_audio_to_text.py"
        env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONIOENCODING': 'utf-8'}
        proc = sub_mod.Popen(
            [python_exe, str(script_path), str(video_file), str(output_dir), video_title, VIDEO_URL],
            stdout=sub_mod.PIPE, stderr=sub_mod.PIPE,
            creationflags=getattr(sub_mod, 'CREATE_NO_WINDOW', 0),
            env=env
        )
        result_file = output_dir / f"_audio_result_{proc.pid}.json"

        # 后台线程：实时读取子进程 stdout 的 STATUS 行 + 轮询进度文件 + 轮询子进程退出
        _poll_stop = False
        _stdout_lines = []
        audio_progress_file = output_dir / f"_audio_progress_{proc.pid}.txt"
        last_audio_pct = -1

        def poll_subprocess():
            nonlocal last_audio_pct
            while not _poll_stop:
                if proc.poll() is not None:
                    break
                # 轮询音频提取进度文件（子进程写入，父进程读）
                try:
                    if audio_progress_file.exists():
                        pct = int(audio_progress_file.read_text(encoding='utf-8').strip())
                        if pct != last_audio_pct and pct > last_audio_pct:
                            last_audio_pct = pct
                except Exception:
                    pass
                # 非阻塞读取 stdout（每次读一行）
                try:
                    raw = proc.stdout.readline()
                    if raw:
                        line = raw.decode('utf-8', errors='replace').strip()
                        if line.startswith('STATUS:'):
                            try:
                                msg = json.loads(line[7:])
                                q.put(json.dumps({"event": "status", "data": msg.get("data", "")}, ensure_ascii=False))
                            except json.JSONDecodeError:
                                pass
                        elif line.startswith('RESULT:'):
                            _stdout_lines.append(line)
                except Exception:
                    pass
                time.sleep(0.5)

        poll_thread = threading.Thread(target=poll_subprocess, daemon=True)
        poll_thread.start()

        try:
            proc.wait(timeout=3600)
        except sub_mod.TimeoutExpired:
            proc.kill()
            proc.wait()
            push("error", "音频转文字超时（超过60分钟）")
            return
        finally:
            _poll_stop = True
            poll_thread.join(timeout=2)

        stderr2 = proc.stderr.read().decode('utf-8', errors='replace')[:500]

        # poll 线程已实时读取了 stdout，结果行存入 _stdout_lines
        # 主线程等待结束后，按以下顺序查找：poll线程已读行 → 结果文件
        txt_result = None

        # 1. 从 poll 线程收集的 RESULT 行（poll 线程在 wait() 期间已读完）
        for line in _stdout_lines:
            if line.startswith('RESULT:'):
                try:
                    txt_result = json.loads(line[7:])
                    break
                except json.JSONDecodeError:
                    pass

        # 2. 备用：结果文件
        result_json = None
        if not txt_result and result_file.exists():
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result_json = json.load(f)
            except Exception as e:
                push("status", f"读取结果文件失败: {e}")
            # 无论读取成功与否，都要删文件
            try:
                result_file.unlink()
            except Exception:
                pass
            if result_json:
                txt_result = result_json

        # 3. 备用2：直接读 proc.stdout（wait() 后 pipe 已关闭，返回空）
        if not txt_result:
            try:
                remaining = proc.stdout.read()
                if remaining:
                    remaining = remaining.decode('utf-8', errors='replace')
                    for line in remaining.split('\n'):
                        if line.strip().startswith('RESULT:'):
                            try:
                                txt_result = json.loads(line[7:])
                                break
                            except json.JSONDecodeError:
                                pass
            except Exception:
                pass

        # 清理音频进度文件
        try:
            audio_progress_file.unlink()
        except Exception:
            pass

        if stderr2:
            push("status", f"转写器stderr前200字: {stderr2[:200]}")

        if not txt_result or not txt_result.get('ok'):
            err2 = txt_result.get('error', '未知错误') if txt_result else '转写器无输出'
            push("error", f"音频转文字失败: {err2}")
            return

        txt_content = txt_result['content']
        txt_file = txt_result['file']
        push("status", "─── 音频转文字完成 ✓ ───")
        push("done", json.dumps({"file": txt_file, "content": txt_content}, ensure_ascii=False))

    except Exception as e:
        import traceback
        traceback.print_exc()
        push("error", f"发生错误: {e}")


# ==================== Flask 最小化实现 ====================
def make_app():
    from flask import Flask, request, Response, stream_with_context
    app = Flask(__name__)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template('index.html')

    @app.route("/save", methods=["POST"])
    def save():
        from flask import request, jsonify
        data = request.get_json()
        file_path = data.get("file", "")
        content = data.get("content", "")

        # 路径安全校验：只允许写入 OUTPUT_DIR 目录
        safe_dir = OUTPUT_DIR.resolve()
        try:
            target = Path(file_path).resolve()
            if not str(target).startswith(str(safe_dir)):
                return jsonify({"ok": False, "error": "非法路径，只能保存到输出目录"}), 400
        except Exception:
            return jsonify({"ok": False, "error": "路径无效"}), 400

        try:
            with open(target, 'w', encoding='utf-8') as f:
                f.write(content)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route("/restart", methods=["POST"])
    def restart():
        # 启动新的 Python 进程运行自身，然后关闭当前进程
        import subprocess
        subprocess.Popen(
            [sys.executable, __file__],
            cwd=str(BASE_DIR),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        os._exit(0)

    @app.route("/transcribe", methods=["GET"])
    def transcribe():
        raw_input = request.args.get("url", "").strip()
        if not raw_input:
            return jsonify({"error": "请输入B站/抖音/小红书视频链接"}), 400

        video_url = parse_video_url(raw_input)
        if not video_url:
            return jsonify({"error": "链接格式错误，请输入B站/抖音/小红书视频链接（如 https://www.bilibili.com/video/BVxxxxx、https://v.douyin.com/xxxxx、https://www.xiaohongshu.com/explore/xxxxx）"}), 400

        q = queue.Queue()
        t = threading.Thread(target=yield_output, args=(q, video_url, OUTPUT_DIR))
        t.daemon = True
        t.start()

        def generate():
            try:
                while True:
                    try:
                        item = q.get(timeout=7200)
                    except queue.Empty:
                        yield f"event: error\ndata: 服务器处理超时\n\n"
                        break
                    msg = json.loads(item)
                    event, data = msg["event"], msg["data"]
                    if event == "done" or event == "error":
                        yield f"event: {event}\ndata: {data}\n\n"
                        break
                    else:
                        yield f"event: status\ndata: {data}\n\n"
            except Exception as e:
                yield f"event: error\ndata: 连接异常: {e}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
        )

    return app


def find_free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_old_progress_files(OUTPUT_DIR)
    # 进程退出时自动清理所有进度文件
    atexit.register(lambda: cleanup_old_progress_files(OUTPUT_DIR))
    port = find_free_port()
    app = make_app()

    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    print("=" * 60)
    print("  B站/抖音视频转文字稿")
    print(f"  访问地址: http://127.0.0.1:{port}")
    print("  关闭窗口即可停止服务")
    print("=" * 60)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
