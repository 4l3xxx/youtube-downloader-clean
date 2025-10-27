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


@app.route("/api/download", methods=["POST", "OPTIONS"])
def api_download():
    if request.method == "OPTIONS":
        return ("", 204)
    # Accept JSON body or form fields
    data = request.get_json(silent=True) if request.is_json else None
    url = (data.get("url") if isinstance(data, dict) else request.values.get("url") or "").strip()
    quality = str((data.get("quality") if isinstance(data, dict) else request.values.get("quality") or "1080")).strip()
    use_async = bool((data.get("async") if isinstance(data, dict) else request.values.get("async")))

    if not url:
        return jsonify({"ok": False, "error": "URL is required"}), 400

    base = yt_dlp_cmd()
    if not base:
        return jsonify({"ok": False, "error": "yt-dlp not installed (binary or Python module)"}), 500

    # For merged MP4 output, require ffmpeg to avoid separate audio/video files
    ffmpeg_ok, ffmpeg_loc = resolve_ffmpeg()
    if not ffmpeg_ok:
        return jsonify({"ok": False, "error": "ffmpeg not detected. Install ffmpeg so video+audio can be merged into one MP4."}), 400

    # Normalize quality -> height
    qmap = {"2160": 2160, "1440": 1440, "1080": 1080, "720": 720, "480": 480, "360": 360, "240": 240, "144": 144}
    height = qmap.get(quality, 1080)

    dl_dir = resolve_download_dir()
    dl_dir.mkdir(parents=True, exist_ok=True)

    fmt = f"bv*[ext=mp4][height<={height}]+ba[ext=m4a]/bv*[height<={height}]+ba/b[ext=mp4][height<={height}]/b[height<={height}]"
    out_tmpl = str(dl_dir / "%(title)s [%(resolution)s]-%(id)s.%(ext)s")

    cmd = base + [
        "--no-playlist",
        "-f", fmt,
        "--remux-video", "mp4",
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        url,
    ]

    # Async mode using yt_dlp Python API with progress (returns JSON)
    if use_async:
        try:
            import yt_dlp
        except Exception as e:
            return jsonify({"ok": False, "error": f"yt-dlp module not available: {e}"}), 500

        task_id = str(int(time.time()*1000))
        TASKS[task_id] = {
            "status": "starting",
            "progress": 0,
            "eta": None,
            "speed": None,
            "title": None,
            "log": "",
            "download_dir": str(dl_dir),
        }

        def hook(d):
            t = TASKS.get(task_id)
            if not t:
                return
            t["status"] = d.get("status", t["status"]) or t["status"]
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = int(downloaded * 100 / total) if total else 0
                t["progress"] = pct
                t["eta"] = d.get("eta")
                t["speed"] = d.get("speed")
                t["title"] = d.get("info_dict", {}).get("title") or t["title"]
            if d.get("status") == "finished":
                t["progress"] = 100
                t["eta"] = 0

        def run():
            fmt_local = fmt
            out_local = out_tmpl
            yopts = {
                "noplaylist": True,
                "format": fmt_local,
                "outtmpl": out_local,
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
                ],
                "progress_hooks": [hook],
                # Reduce console noise
                "quiet": True,
                "no_warnings": True,
            }
            try:
                with yt_dlp.YoutubeDL(yopts) as ydl:
                    ydl.download([url])
                TASKS[task_id]["status"] = "completed"
            except Exception as e:
                TASKS[task_id]["status"] = "error"
                TASKS[task_id]["log"] = str(e)

        threading.Thread(target=run, daemon=True).start()
        return jsonify({"ok": True, "task_id": task_id, "download_dir": str(dl_dir)})

    # File-returning mode: download to temp/ then stream file to client and delete
    try:
        temp_dir = Path.cwd() / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Prefer MP4; final naming will be captured via hook
        fmt_local = fmt
        out_tmpl = str(temp_dir / "%(title)s [%(resolution)s]-%(id)s.%(ext)s")

        final_path_holder: dict[str, str | None] = {"path": None}

        def hook(d):
            if d.get("status") == "finished":
                # yt-dlp sets 'filename' to the final file after postprocessing
                fp = d.get("filename") or d.get("info_dict", {}).get("_filename")
                if fp:
                    final_path_holder["path"] = fp

        try:
            import yt_dlp  # type: ignore
        except Exception as e:
            return jsonify({"ok": False, "error": f"yt-dlp module not available: {e}"}), 500

        yopts: dict = {
            "noplaylist": True,
            "format": fmt_local,
            "outtmpl": out_tmpl,
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
            ],
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
        }
        if ffmpeg_loc:
            yopts["ffmpeg_location"] = ffmpeg_loc

        with yt_dlp.YoutubeDL(yopts) as ydl:
            ydl.download([url])

        # Determine the final path
        final_path = final_path_holder.get("path")
        if not final_path:
            # Fallback: pick the most recent file in temp_dir
            cand = sorted(temp_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            final_path = str(cand[0]) if cand else None

        if not final_path or not Path(final_path).exists():
            return jsonify({"ok": False, "error": "Download finished but file not found."}), 500

        dl_name = Path(final_path).name

        @after_this_request
        def _cleanup(resp):
            try:
                Path(final_path).unlink(missing_ok=True)
            except Exception:
                pass
            return resp

        # Send as attachment so the browser/WebView saves to Downloads
        return send_file(final_path, as_attachment=True, download_name=dl_name, mimetype="video/mp4")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
