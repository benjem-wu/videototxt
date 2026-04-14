"""
音频转文字 - 独立进程模块
功能：提取音频 → Whisper转写 → 保存TXT
由 b_site_launcher.py 调用，单独进程运行
"""
import os
import sys
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime

from _utils import check_path_length

# 强制行缓冲 + UTF-8 输出
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print(f"AUDIO_TO_TEXT_BOOT pid={os.getpid()}", flush=True)

# ============ 配置 ============
FFMPEG_PATH = Path(__file__).parent / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe"
WHISPER_MODEL = "large-v3"
CUDA_BIN = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin"
HF_ENDPOINT = "https://hf-mirror.com"

# Whisper 模型单例缓存（避免重复加载占用GPU显存）
_whisper_model_cache = None


def add_punctuation(text):
    """为连续文字添加中文标点"""
    if not text or not text.strip():
        return text
    words = text.split()
    result, current, char_count = [], [], 0
    for word in words:
        current.append(word)
        char_count += len(word)
        if char_count >= 25:
            result.append(''.join(current))
            current = []
            char_count = 0
    if current:
        result.append(''.join(current))
    final = '，'.join(result)
    if final and final[-1] not in '。！？':
        final += '。'
    return final


def format_as_article(segments, max_gap=3.0, min_para_len=2):
    """按语义聚合成文章分段"""
    if not segments:
        return []
    paragraphs, current_para, last_end = [], [], 0.0
    for seg in segments:
        text = seg['text'].strip()
        if not text:
            continue
        gap = seg['start'] - last_end
        if gap > max_gap and len(current_para) >= min_para_len:
            paragraphs.append(' '.join(current_para))
            current_para = [text]
        else:
            current_para.append(text)
        last_end = seg['end']
    if current_para:
        paragraphs.append(' '.join(current_para))
    return paragraphs


def process(video_file_str, output_dir_str, video_title_str, video_url_str):
    """主处理函数：音频提取 → Whisper转写 → 保存TXT"""
    video_file = Path(video_file_str)
    output_dir = Path(output_dir_str)
    video_title = video_title_str
    video_url = video_url_str
    pid = os.getpid()

    def push(event, data=""):
        msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        print(f"STATUS:{msg}", flush=True)

    def write_progress(pct):
        try:
            with open(str(output_dir / f"_audio_progress_{pid}.txt"), 'w', encoding='utf-8') as f:
                f.write(str(int(pct)))
        except Exception:
            pass

    try:
        # ---- 设置环境变量 ----
        ffmpeg_dir = str(FFMPEG_PATH.parent)
        env_path = ffmpeg_dir + os.pathsep + CUDA_BIN + os.pathsep + os.environ.get("PATH", "")
        os.environ["PATH"] = env_path
        os.environ["HF_ENDPOINT"] = HF_ENDPOINT

        # ---- 提取音频 ----
        audio_path = output_dir / "audio.wav"

        # 先用 ffprobe 获取视频总时长（用于进度计算）
        probe_cmd = [
            str(FFMPEG_PATH.parent / "ffprobe.exe"),
            "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(video_file)
        ]
        try:
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True,
                                         encoding='utf-8', errors='replace')
            total_dur = float(probe_result.stdout.strip() or 0)
        except Exception:
            total_dur = 0

        push("status", "[1%] 正在提取音频...")
        write_progress(1)

        # 用 Popen + -progress 实时追踪进度
        cmd = [
            str(FFMPEG_PATH),
            "-i", str(video_file),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", "-y",
            "-progress", "pipe:1",
            str(audio_path)
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                encoding='utf-8', errors='replace')
        last_pct = 1
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    ms = int(line.split("=", 1)[1])
                    cur_sec = ms / 1_000_000
                    if total_dur > 0:
                        pct = min(99, int(cur_sec / total_dur * 100))
                        if pct != last_pct:
                            push("status", f"[{pct}%] 正在提取音频...")
                            write_progress(pct)
                            last_pct = pct
                except Exception:
                    pass
            elif line == "progress=end":
                break
        proc.wait()
        if proc.returncode != 0:
            write_progress(0)
            return {"ok": False, "error": f"音频提取失败"}
        write_progress(100)
        push("status", "[100%] 音频提取完成")
        push("status", "─── 音频提取完成 ✓ ───")

        # ---- 加载Whisper模型（OOM时自动降级到int8）----
        push("status", f"[2%] 正在加载 Whisper {WHISPER_MODEL} 模型...")
        import faster_whisper
        import threading
        global _whisper_model_cache
        if _whisper_model_cache is None:
            for compute_type in ("float16", "int8"):
                try:
                    _whisper_model_cache = faster_whisper.WhisperModel(
                        WHISPER_MODEL, device="cuda", compute_type=compute_type
                    )
                    push("status", f"[2%] 模型加载成功（compute_type={compute_type}）")
                    break
                except Exception as e:
                    if compute_type == "int8":
                        raise  # int8也失败则上抛
                    push("status", f"float16加载失败，尝试降级到int8: {e}")
        model = _whisper_model_cache
        push("status", "[5%] 模型加载完成，开始识别...")

        # ---- 转写 ----
        segments, info = model.transcribe(
            str(audio_path),
            language='zh',
            task='transcribe',
            vad_filter=False,
        )

        total_duration = info.duration  # 总音频秒数
        total_minutes = total_duration / 60
        _transcribe_start_time = time.time()
        push("status", f"[5%] 音频总时长 {total_minutes:.1f} 分钟，开始转写...")

        whisper_segments = []
        last_push_time = time.time()
        last_end_time = 0.0
        recent_ends = []  # 最近几段的结束时间，用于估算速度

        for s in segments:
            whisper_segments.append({'start': s.start, 'end': s.end, 'text': s.text})
            last_end_time = s.end
            seg_count = len(whisper_segments)
            now = time.time()

            # 每5秒推送一次进度，或每20段推送一次
            if seg_count % 20 == 0 or (now - last_push_time) > 5:
                pct = min(100, int(last_end_time / total_duration * 100)) if total_duration else 0
                recent_ends.append(last_end_time)
                if len(recent_ends) > 10:
                    recent_ends.pop(0)
                # 根据最近片段估算每秒处理音频量
                if len(recent_ends) >= 3:
                    span = recent_ends[-1] - recent_ends[0]
                    span_t = now - last_push_time
                    if span > 0 and span_t > 0:
                        audio_per_sec = span / span_t
                        remaining_audio = total_duration - last_end_time
                        eta_sec = remaining_audio / audio_per_sec if audio_per_sec > 0 else 0
                        eta_str = f"约剩{int(eta_sec)}秒"
                    else:
                        eta_str = ""
                else:
                    eta_str = ""

                status_text = f"[{pct}%] 转写中 {seg_count}段/{total_minutes:.1f}分钟"
                if eta_str:
                    status_text += f"，{eta_str}"
                push("status", status_text)
                write_progress(5 + pct * 0.9)  # 转写占总进度 5%~95%
                last_push_time = now

        write_progress(100)
        push("status", f"[100%] 转写完成，{len(whisper_segments)}段（语言:{info.language}，置信度:{info.language_probability:.2f}）")

        # ---- 整理输出 ----
        push("status", "[100%] 正在保存文字稿...")
        paragraphs = format_as_article(whisper_segments)
        punctuated = [add_punctuation(p) for p in paragraphs]
        txt_file = output_dir / f"{video_title}_文字稿.txt"
        header = (
            f"# {video_title}\n"
            f"来源: {video_url}\n"
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"原始段落数: {len(whisper_segments)}，聚合后段落数: {len(paragraphs)}\n"
            + "=" * 60 + "\n\n"
        )
        body = "\n\n".join(punctuated)
        full_content = header + body

        # 路径长度检查，防止 Windows MAX_PATH 问题
        ok, err = check_path_length(txt_file)
        if not ok:
            push("status", f"[100%] 路径过长，自动缩短标题重试...")
            # 截断标题后重试
            short_title = video_title[:80]
            txt_file = output_dir / f"{short_title}_文字稿.txt"
            ok2, err2 = check_path_length(txt_file)
            if not ok2:
                return {"ok": False, "error": f"路径长度问题: {err2}"}

        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(full_content)
        push("status", f"TXT已保存: {txt_file.name}")

        # ---- 清理临时文件 ----
        for f in output_dir.glob(f"{video_title}.*"):
            try:
                f.unlink()
            except Exception:
                pass
        audio_wav = output_dir / "audio.wav"
        if audio_wav.exists():
            try:
                audio_wav.unlink()
            except Exception:
                pass
        # 清理进度文件
        try:
            (output_dir / f"_audio_progress_{pid}.txt").unlink()
        except Exception:
            pass

        return {"ok": True, "file": str(txt_file), "content": full_content}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    print(f"AUDIO_TO_TEXT_START pid={os.getpid()}", flush=True)
    try:
        video_file = sys.argv[1]
        output_dir = Path(sys.argv[2])
        video_title = sys.argv[3]
        video_url = sys.argv[4]

        # 结果文件（通过文件传递结果，避免 stdout pipe 编码问题）
        result_file = output_dir / f"_audio_result_{os.getpid()}.json"
        print(f"ARGS video_file={video_file}", flush=True)
        print(f"RESULT_FILE={result_file}", flush=True)

        result = process(video_file, output_dir, video_title, video_url)

        # 写结果文件（可靠传递）
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)

        # 同时打印 RESULT: 行（用于兼容）
        print("RESULT:" + json.dumps(result, ensure_ascii=False), flush=True)

        sys.stdout.flush()
        sys.stderr.flush()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: {e}", flush=True)
        sys.exit(1)
