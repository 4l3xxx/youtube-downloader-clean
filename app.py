import os
import platform
import shutil
import subprocess
import sys
import importlib.util
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file, after_this_request
from werkzeug.utils import secure_filename
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
    # cookies status: prefer file in project root, fallback to temp cookies dir
    project_root = os.path.dirname(os.path.abspath(__file__))
    root_cookie = os.path.join(project_root, "youtube.com_cookies.txt")
    tmp_cookie_dir = os.path.join(tempfile.gettempdir(), "cookies")
    tmp_cookie = os.path.join(tmp_cookie_dir, "youtube.com_cookies.txt")
    cpath = root_cookie if os.path.exists(root_cookie) else (tmp_cookie if os.path.exists(tmp_cookie) else None)
    return jsonify({
        "status": "ok",
        "yt_dlp": bool(yt_dlp_cmd()),
        "ffmpeg": ff_ok,
        "ffmpeg_location": ff_loc,
        "download_dir": str(resolve_download_dir()),
        "cookies_present": bool(cpath),
        "cookies_path": cpath,
    })


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "URL is required"}, 400
    quality = (data.get("quality") or "1080p").rstrip("p")
    use_async = bool(data.get("async"))
    preferred_browser = (data.get("cookies_from_browser") or data.get("browser") or "").strip().lower() or None

    tmpdir = os.path.join(tempfile.gettempdir(), "ytdl")
    os.makedirs(tmpdir, exist_ok=True)

    # Common yt-dlp options
    ydl_base_opts = {
        "paths": {"home": tmpdir},
        "outtmpl": {"default": "%(title)s.%(ext)s"},
        "restrictfilenames": True,
        "merge_output_format": "mp4",
        "format": f"bestvideo[height<={quality}]+bestaudio/best",
        # quieter logs in production
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
    }
    # If cookies present, prefer project-level youtube.com_cookies.txt, else temp upload
    project_root = os.path.dirname(os.path.abspath(__file__))
    root_cookie = os.path.join(project_root, "youtube.com_cookies.txt")
    cookies_dir = os.path.join(tempfile.gettempdir(), "cookies")
    tmp_cookie = os.path.join(cookies_dir, "youtube.com_cookies.txt")
    cookie_path = root_cookie if os.path.exists(root_cookie) else (tmp_cookie if os.path.exists(tmp_cookie) else None)
    if cookie_path:
        ydl_base_opts["cookiefile"] = cookie_path

    # Async mode for Railway (avoid timeouts): start task and poll progress/result
    # Helper: decide if error indicates login/cookies required
    def _is_auth_error(err_msg: str) -> bool:
        m = (err_msg or "").lower()
        tokens = [
            "sign in to confirm",
            "please sign in",
            "cookies",
            "consent",
            "verify you are",
            "not a bot",
            "access denied",
        ]
        return any(t in m for t in tokens)

    # Helper: attempt download with optional cookies-from-browser
    def _attempt_with_browser(browser: str | None, hook=None):
        opts = dict(ydl_base_opts)
        if hook:
            opts["postprocessor_hooks"] = [hook]
        if browser:
            # yt-dlp expects tuple; minimal (browser,) works for most cases
            opts["cookiesfrombrowser"] = (browser,)
        with YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)

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
                # First attempt (no browser cookies if cookiefile already set)
                try:
                    _attempt_with_browser(None, hook)
                    TASKS[task_id]["status"] = "completed"
                    return
                except Exception as e1:
                    msg = str(e1)
                    # Retry with cookies-from-browser if requested or auth-like error
                    retry_browsers = []
                    if preferred_browser:
                        retry_browsers.append(preferred_browser)
                    # simple OS-based guess if not provided
                    if not retry_browsers and _is_auth_error(msg):
                        sysname = platform.system().lower()
                        if sysname.startswith("win"):
                            retry_browsers = ["chrome", "edge", "firefox"]
                        elif sysname == "darwin":
                            retry_browsers = ["chrome", "safari", "firefox"]
                        else:
                            retry_browsers = ["chrome", "chromium", "firefox"]
                    # Perform retries
                    for b in retry_browsers:
                        try:
                            _attempt_with_browser(b, hook)
                            TASKS[task_id]["status"] = "completed"
                            TASKS[task_id]["log"] = f"Used cookies from browser: {b}"
                            return
                        except Exception as _:
                            continue
                    # If we reach here, fail with guidance
                    TASKS[task_id]["status"] = "error"
                    TASKS[task_id]["log"] = (
                        msg
                        + "\nHint: Provide cookies — upload cookies.txt via /api/upload_cookies or set 'cookies_from_browser' to 'chrome' or 'firefox'."
                    )

        threading.Thread(target=run, daemon=True).start()
        return jsonify({"ok": True, "task_id": task_id})

    # Sync mode: download and stream file immediately
    final = {"path": None}

    def pp_hook(d):
        if d.get("status") == "finished":
            info = d.get("info_dict") or {}
            final["path"] = info.get("filepath")

    # Sync path with retry logic
    try:
        _attempt_with_browser(None, pp_hook)
    except Exception as e1:
        msg = str(e1)
        retry_browsers = []
        if preferred_browser:
            retry_browsers.append(preferred_browser)
        if not retry_browsers and _is_auth_error(msg):
            sysname = platform.system().lower()
            if sysname.startswith("win"):
                retry_browsers = ["chrome", "edge", "firefox"]
            elif sysname == "darwin":
                retry_browsers = ["chrome", "safari", "firefox"]
            else:
                retry_browsers = ["chrome", "chromium", "firefox"]
        for b in retry_browsers:
            try:
                _attempt_with_browser(b, pp_hook)
                break
            except Exception:
                continue
        else:
            return {"ok": False, "error": msg + "\nPlease provide browser cookies (chrome/firefox) or upload cookies.txt."}, 400

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

@app.post("/api/upload_cookies")
def upload_cookies():
    # Accept multipart/form-data with field name 'file' or 'cookies'
    if not request.files:
        return {"ok": False, "error": "No file uploaded"}, 400
    f = request.files.get("file") or request.files.get("cookies")
    if not f:
        return {"ok": False, "error": "Missing file field (expected 'file' or 'cookies')"}, 400

    domain = (request.form.get("domain") or "youtube.com").strip()
    # Sanitize filename; default to youtube.com_cookies.txt
    base_name = request.form.get("name") or f.filename or f"{domain}_cookies.txt"
    base_name = secure_filename(base_name) or f"{domain}_cookies.txt"
    # Normalize to standard name for auto-pickup
    if not base_name.lower().endswith("_cookies.txt"):
        base_name = f"{domain}_cookies.txt"

    cdir = os.path.join(tempfile.gettempdir(), "cookies")
    os.makedirs(cdir, exist_ok=True)
    save_path = os.path.join(cdir, base_name)

    f.save(save_path)
    size = os.path.getsize(save_path)
    return jsonify({
        "ok": True,
        "path": save_path,
        "size": size,
        "note": "This cookies file will be used automatically for future downloads.",
    })

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
