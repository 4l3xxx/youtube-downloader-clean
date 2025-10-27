Hybrid Deployment Guide

Backend (Flask)
- Requirements: yt-dlp, ffmpeg available on the host.
- App binds to 0.0.0.0 and enables CORS for all routes.

Run locally
  pip install -r requirements.txt
  python app.py              # uses PORT env or 5231

Production (examples)
- Render/Railway/Fly/VM:
  - Ensure ffmpeg is installed in the image/host.
  - Set PORT env (platforms usually inject it). The app reads PORT.
  - Start command:
      gunicorn -w 2 -b 0.0.0.0:$PORT app:app

Notes
- If ffmpeg is not in PATH, set FFMPEG_LOCATION to its bin folder.
- / serves web/index.html and /web assets; APIs under /api/*

Flutter WebView App
- See flutter_webview/README.md. Build the APK pointing to your deployed URL:
  flutter build apk --release \
    --dart-define=INITIAL_URL=https://yourapp.onrender.com

