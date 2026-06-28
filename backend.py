"""
MiMo STT Backend - Speech-to-Text using Xiaomi MiMo multimodal API
Supports common audio/video formats, segments long files into 60s chunks.
"""

import os
import sys
import json
import time
import uuid
import base64
import wave
import subprocess
import threading
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

# ── Config ──────────────────────────────────────────────────────────────────
DEFAULT_API_KEY = ""
DEFAULT_API_ENDPOINT = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
SEGMENT_DURATION = 60        # seconds per chunk
REQUEST_TIMEOUT = 120        # seconds per API call
MAX_COMPLETION_TOKENS = 4096
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2             # 16-bit = 2 bytes
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

SUPPORTED_EXTENSIONS = {
    '.mp3', '.wav', '.flac', '.m4a', '.ogg',
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts', '.flv', '.wmv',
    '.aac', '.wma', '.opus',
}

app = Flask(__name__, static_folder="frontend")
CORS(app)

# ── Task Store ──────────────────────────────────────────────────────────────
tasks = {}  # task_id -> {status, progress, total, result, error, filename}
output_dir = DEFAULT_OUTPUT_DIR  # can be changed via API


# ── Audio Processing ────────────────────────────────────────────────────────
def get_audio_duration(wav_path: str) -> float:
    with wave.open(wav_path, 'rb') as wf:
        return wf.getnframes() / wf.getframerate()


def extract_audio(input_path: str, output_path: str) -> None:
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-ac', str(CHANNELS), '-ar', str(SAMPLE_RATE),
        '-sample_fmt', 's16', '-f', 'wav', output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")


def split_wav(wav_path: str, segment_sec: int, tmp_dir: str) -> list:
    duration = get_audio_duration(wav_path)
    segments = []
    start = 0.0
    idx = 0
    while start < duration:
        end = min(start + segment_sec, duration)
        out_path = os.path.join(tmp_dir, f"seg_{idx:04d}.wav")
        cmd = [
            'ffmpeg', '-y', '-i', wav_path,
            '-ss', str(start), '-to', str(end),
            '-ac', str(CHANNELS), '-ar', str(SAMPLE_RATE),
            '-sample_fmt', 's16', '-f', 'wav', out_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 44:
            segments.append(out_path)
        start = end
        idx += 1
    return segments


def wav_to_base64(wav_path: str) -> str:
    with open(wav_path, 'rb') as f:
        data = f.read()
    b64 = base64.b64encode(data).decode('utf-8')
    return f"data:audio/wav;base64,{b64}"


def call_mimo_api(audio_b64_uri: str, model: str, prompt: str,
                  api_key: str = DEFAULT_API_KEY, api_endpoint: str = DEFAULT_API_ENDPOINT) -> str:
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional speech-to-text transcription engine. "
                    "Transcribe the audio content accurately. "
                    "Output ONLY the transcribed text, nothing else. "
                    "Do not add any explanations, descriptions, or formatting."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_b64_uri}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }
    resp = requests.post(api_endpoint, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]["message"]
    content = (choice.get("content") or "").strip()
    reasoning = (choice.get("reasoning_content") or "").strip()

    if content:
        return content
    if reasoning:
        return reasoning
    return ""


def save_as_markdown(filename: str, result_text: str, segments: list, out_dir: str) -> str:
    """Save transcription result as a markdown file. Returns the file path."""
    os.makedirs(out_dir, exist_ok=True)
    base_name = Path(filename).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_filename = f"{base_name}_{timestamp}.md"
    md_path = os.path.join(out_dir, md_filename)

    lines = []
    lines.append(f"# 转录结果: {filename}\n")
    lines.append(f"- **转录时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"- **分段数量**: {len(segments)}\n")
    lines.append("---\n\n")
    lines.append("## 完整文本\n\n")
    lines.append(result_text)
    lines.append("\n\n")

    if segments and len(segments) > 1:
        lines.append("---\n\n")
        lines.append("## 分段详情\n\n")
        for i, seg in enumerate(segments):
            if seg.strip():
                lines.append(f"### 第 {i + 1} 段\n\n")
                lines.append(seg)
                lines.append("\n\n")

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("".join(lines))

    return md_path


def process_task(task_id: str, file_path: str, model: str, prompt: str,
                 api_key: str = DEFAULT_API_KEY, api_endpoint: str = DEFAULT_API_ENDPOINT):
    task = tasks[task_id]
    tmp_dir = tempfile.mkdtemp(prefix="mimo_stt_")
    try:
        task["status"] = "extracting"
        task["message"] = "正在提取音频..."
        wav_path = os.path.join(tmp_dir, "audio.wav")
        extract_audio(file_path, wav_path)

        task["status"] = "segmenting"
        duration = get_audio_duration(wav_path)
        task["message"] = f"音频时长 {duration:.1f}s，正在分段..."
        segments = split_wav(wav_path, SEGMENT_DURATION, tmp_dir)
        task["total"] = len(segments)
        task["progress"] = 0
        task["results"] = [""] * len(segments)

        task["status"] = "transcribing"
        for i, seg_path in enumerate(segments):
            task["message"] = f"正在转录第 {i+1}/{len(segments)} 段..."
            b64_uri = wav_to_base64(seg_path)
            text = call_mimo_api(b64_uri, model, prompt, api_key, api_endpoint)
            task["results"][i] = text
            task["progress"] = i + 1

        task["status"] = "done"
        full_text = "\n".join(t for t in task["results"] if t)
        task["result"] = full_text
        task["message"] = "转录完成"

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)
        task["message"] = f"错误: {e}"
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("frontend", path)


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify({"error": f"Unsupported format: {ext}"}), 400

    model = request.form.get("model", "mimo-v2.5")
    prompt = request.form.get("prompt", "请将音频中的语音内容逐字转录为文本。只输出转录文本，不要添加任何额外说明。")
    api_key = request.form.get("api_key", DEFAULT_API_KEY)
    api_endpoint = request.form.get("api_endpoint", DEFAULT_API_ENDPOINT)

    task_id = uuid.uuid4().hex[:12]
    upload_dir = tempfile.mkdtemp(prefix="mimo_upload_")
    file_path = os.path.join(upload_dir, f"{task_id}{ext}")
    file.save(file_path)

    tasks[task_id] = {
        "status": "queued",
        "progress": 0,
        "total": 0,
        "result": "",
        "error": "",
        "message": "排队中...",
        "filename": file.filename,
        "results": [],
        "upload_dir": upload_dir,
    }

    thread = threading.Thread(
        target=process_task, args=(task_id, file_path, model, prompt, api_key, api_endpoint), daemon=True
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({
        "status": task["status"],
        "progress": task["progress"],
        "total": task["total"],
        "result": task["result"],
        "error": task["error"],
        "message": task["message"],
        "filename": task["filename"],
        "segments": task.get("results", []),
    })


@app.route("/api/save", methods=["POST"])
def save_result():
    """Save transcription result as markdown file."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    task_id = data.get("task_id")
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task["status"] != "done":
        return jsonify({"error": "Task not completed"}), 400

    save_dir = data.get("output_dir", output_dir)

    try:
        md_path = save_as_markdown(
            task["filename"], task["result"], task.get("results", []), save_dir
        )
        return jsonify({"path": md_path, "message": f"已保存到 {md_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/set-output-dir", methods=["POST"])
def set_output_dir():
    """Set the default output directory."""
    global output_dir
    data = request.get_json()
    new_dir = data.get("output_dir", "")
    if not new_dir:
        return jsonify({"error": "Empty path"}), 400
    output_dir = new_dir
    os.makedirs(output_dir, exist_ok=True)
    return jsonify({"output_dir": output_dir})


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    """Gracefully shut down the server."""
    def _shutdown():
        time.sleep(0.3)
        print("\n" + "=" * 50)
        print("  服务已通过网页端关闭")
        print("=" * 50)
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return jsonify({"message": "服务正在关闭..."})


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Fix console encoding for Chinese Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    print("=" * 60)
    print("  MiMo STT - Speech to Text")
    print(f"  URL:  http://localhost:5000")
    print(f"  Output: {DEFAULT_OUTPUT_DIR}")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
