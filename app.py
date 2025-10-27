import os
import platform
import shutil
import subprocess
import sys
import importlib.util
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file, after_this_request
from flask_cors import CORS
import threading
import time
import tempfile
from yt_dlp import YoutubeDL


def resolve_download_dir() -> Path:
    sysname = platform.system().lower()
    home = Path.home()

    # Windows
    if sysname.startswith("win"):
        dl = Path(os.environ.get("USERPROFILE", str(home))) / "Downloads"
        return dl if dl.exists() else Path.cwd()

    # Android via Termux
    # Common Termux storage paths
    termux_dl = Path.home() / "storage" / "downloads"
    if termux_dl.exists():
        return termux_dl
    sd_dl = Path("/sdcard/Download")
    if sd_dl.exists():
        return sd_dl

    # Linux/macOS default
    dl = home / "Downloads"
    return dl if dl.exists() else Path.cwd()


def bin_exists(name: str) -> bool:
    return shutil.which(name) is not None


def resolve_ffmpeg():
    """Return (ok, location) where location is a directory containing ffmpeg.
    Checks PATH, env vars, and scans common Windows install locations.
    """
    exe_name = "ffmpeg.exe" if platform.system().lower().startswith("win") else "ffmpeg"

    # 1) PATH
    p = shutil.which("ffmpeg")
    if p:
        return True, os.path.dirname(p)

    # 2) Environment variables
    for env in ("FFMPEG_LOCATION", "FFMPEG_BIN", "FFMPEG_PATH"):
        val = os.environ.get(env)
        if not val:
            continue
        path = Path(val)
        if path.is_file() and path.name.lower() == exe_name:
            return True, str(path.parent)
        if path.is_dir():
            exe = path / exe_name
            if exe.exists():
                return True, str(path)

    # 3) Known Windows locations (WinGet, Chocolatey, manual C:\ffmpeg, Program Files, Scoop)
    if platform.system().lower().startswith("win"):
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
            Path("C:/ffmpeg/bin"),
            Path("C:/ffmpeg"),
            Path("C:/ProgramData/chocolatey"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin",
        ]
        for root in candidates:
            try:
                if not root.exists():
                    continue
                # Search shallow first
                direct = root / exe_name
                if direct.exists():
                    return True, str(root)
                # Then recursive but bounded by depth via rglob
                for hit in root.rglob(exe_name):
                    return True, str(hit.parent)
            except Exception:
                continue

    return False, None


def module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def yt_dlp_cmd():
    # Prefer system binary if available
    if bin_exists("yt-dlp"):
        return ["yt-dlp"]
    # Fallback to Python module (works if yt-dlp installed in current interpreter/venv)
    if module_exists("yt_dlp"):
        return [sys.executable, "-m", "yt_dlp"]
    return None


app = Flask(__name__, static_folder="web", static_url_path="/")
CORS(app, resources={r"/*": {"origins": "*"}})


@app.after_request
def add_cors(resp):
    # Allow using file:// opened index.html to call the API
    resp.headers.setdefault("Access-Control-Allow-Origin", "*")
    resp.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
    resp.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return resp


@app.get("/")
def index():
    return send_file(Path(app.static_folder) / "index.html")


@app.get("/api/health")
def health():
    ff_ok, ff_loc = resolve_ffmpeg()
    return jsonify({
        "status": "ok",
        "yt_dlp": bool(yt_dlp_cmd()),
        "ffmpeg": ff_ok,
        "ffmpeg_location": ff_loc,
        "download_dir": str(resolve_download_dir()),
    })


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "URL is required"}, 400
    quality = (data.get("quality") or "1080p").rstrip("p")
    use_async = bool(data.get("async"))

    tmpdir = os.path.join(tempfile.gettempdir(), "ytdl")
    os.makedirs(tmpdir, exist_ok=True)

    # Common yt-dlp options
    ydl_base_opts = {
        "paths": {"home": tmpdir},
        "outtmpl": {"default": "%(title)s [%(id)s].%(ext)s"},
        "restrictfilenames": True,
        "merge_output_format": "mp4",
        "format": f"bestvideo[height<={quality}]+bestaudio/best",
        # quieter logs in production
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
    }

    # Async mode for Railway (avoid timeouts): start task and poll progress/result
    if use_async:
        task_id = str(int(time.time() * 1000))
        TASKS[task_id] = {
            "status": "starting",
            "progress": 0,
            "eta": None,
            "speed": None,
            "title": None,
            "log": "",
            "file": None,
        }

        def hook(d):
            t = TASKS.get(task_id)
            if not t:
                return
            st = d.get("status")
            if st:
                t["status"] = st
            if st == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                t["progress"] = int(downloaded * 100 / total) if total else 0
                t["eta"] = d.get("eta")
                t["speed"] = d.get("speed")
                t["title"] = d.get("info_dict", {}).get("title") or t.get("title")
            if st == "finished":
                info = d.get("info_dict") or {}
                fp = info.get("filepath") or info.get("_filename")
                if fp:
                    t["file"] = fp
                t["progress"] = 100

        def run():
            try:
                opts = dict(ydl_base_opts)
                opts["postprocessor_hooks"] = [hook]
                with YoutubeDL(opts) as ydl:
                    ydl.extract_info(url, download=True)
                TASKS[task_id]["status"] = "completed"
            except Exception as e:
                TASKS[task_id]["status"] = "error"
                TASKS[task_id]["log"] = str(e)

        threading.Thread(target=run, daemon=True).start()
        return jsonify({"ok": True, "task_id": task_id})

    # Sync mode: download and stream file immediately
    final = {"path": None}

    def pp_hook(d):
        if d.get("status") == "finished":
            info = d.get("info_dict") or {}
            final["path"] = info.get("filepath")

    opts = dict(ydl_base_opts)
    opts["postprocessor_hooks"] = [pp_hook]
    with YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)

    fp = final["path"]
    if not fp or not os.path.exists(fp):
        cand = sorted(
            (os.path.join(tmpdir, f) for f in os.listdir(tmpdir)),
            key=os.path.getmtime, reverse=True
        )
        fp = next((p for p in cand if p.lower().endswith((".mp4", ".mkv", ".webm"))), None)

    if not fp or not os.path.exists(fp):
        return {"ok": False, "error": "Download finished but file not found."}, 500

    basename = os.path.basename(fp)

    @after_this_request
    def _cleanup(resp):
        try:
            os.remove(fp)
        except Exception:
            pass
        return resp

    return send_file(fp, as_attachment=True, download_name=basename, mimetype="video/mp4", conditional=True)

@app.get("/api/result")
def api_result():
    tid = request.args.get("task")
    t = TASKS.get(tid or "")
    if not t:
        return {"ok": False, "error": "task not found"}, 404
    if t.get("status") != "completed":
        return {"ok": False, "error": "task not completed"}, 400
    fp = t.get("file")
    if not fp or not os.path.exists(fp):
        return {"ok": False, "error": "file not found"}, 404
    basename = os.path.basename(fp)

    @after_this_request
    def _cleanup(resp):
        try:
            os.remove(fp)
        except Exception:
            pass
        # Optionally clear task entry
        try:
            TASKS.pop(tid, None)
        except Exception:
            pass
        return resp

    return send_file(fp, as_attachment=True, download_name=basename, mimetype="video/mp4", conditional=True)


@app.get("/dl")
def show_dl_path():
    # Small helper to expose path info in UI
    return jsonify({"download_dir": str(resolve_download_dir())})


# In-memory task store for async progress
TASKS: dict[str, dict] = {}


@app.get("/api/progress")
def api_progress():
    tid = request.args.get("task")
    t = TASKS.get(tid or "")
    if not t:
        return jsonify({"ok": False, "error": "task not found"}), 404
    return jsonify({"ok": True, **t})


def main():
    port = int(os.environ.get("PORT", "5231"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
