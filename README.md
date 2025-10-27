Personal YouTube Downloader (yt-dlp + ffmpeg)

What you get
- Single MP4 output (video+audio merged)
- Quality picker: 144p up to 4K (if available)
- Auto-saves to Downloads
  - Windows: %USERPROFILE%\Downloads
  - Linux/macOS: ~/Downloads
  - Android (Termux): storage downloads folder so it shows up in Gallery
- No ads, personal use only

Files
- win-ytmp4.bat: Windows batch script (interactive)
- ytmp4.sh: Linux/macOS shell script (interactive)
- termux-ytmp4.sh: Minimal Termux script (URL + optional height)
- app.py + web/: Simple GUI (web-app) served by Flask

Install prerequisites
Windows
- Option A (portable):
  1) Download yt-dlp.exe: https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
  2) Download ffmpeg (zip): https://www.gyan.dev/ffmpeg/builds/ or https://www.ffmpeg.org/download.html
  3) Put yt-dlp.exe and ffmpeg\bin in PATH (or in the same folder as win-ytmp4.bat)
- Option B (package manager):
  - winget install yt-dlp.yt-dlp Gyan.FFmpeg   (or)
  - choco install yt-dlp ffmpeg

Linux
- Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y yt-dlp ffmpeg
- Arch: sudo pacman -S yt-dlp ffmpeg
- Fedora: sudo dnf install yt-dlp ffmpeg

macOS
- Using Homebrew: brew install yt-dlp ffmpeg

Android (Termux)
1) Install Termux from F-Droid
2) In Termux, run:
   pkg update && pkg install -y yt-dlp ffmpeg
   termux-setup-storage   # grant access to /sdcard/Download

Usage
GUI (Web App, recommended)
- Start backend: python app.py
- Open http://127.0.0.1:5231 in your browser (Windows/macOS/Linux/Android)
- Paste URL, choose quality, click Download. Files save to your Downloads.

Windows
- Double-click win-ytmp4.bat, paste the YouTube URL, pick quality, done.

Linux/macOS
- Make script executable and run:
  chmod +x ytmp4.sh
  ./ytmp4.sh

Termux (Android)
- Make script executable and run (URL first, optional height second):
  chmod +x termux-ytmp4.sh
  ./termux-ytmp4.sh "https://www.youtube.com/watch?v=..." 1080
- If you omit the height, it defaults to 1080. Use 2160 for 4K, 720, 480, 360, etc.

Android GUI via Termux (optional)
- Install Python and Flask, then run the web app locally:
  pkg install -y python
  pip install flask
  python app.py
- Buka http://127.0.0.1:5231 di browser HP kamu.

Notes
- The scripts prefer MP4 video and M4A audio, then remux to MP4. If only non-MP4 codecs are available, yt-dlp may remux; if it cannot, consider switching quality or adding --recode-video mp4 (slower).
- --no-playlist is used so a single video is downloaded even if the URL contains a playlist parameter.
- Filenames look like: Title [WIDTHxHEIGHT]-VIDEOID.mp4 in your Downloads.

Troubleshooting
- ffmpeg not found: install ffmpeg so yt-dlp can merge/remux streams into a single MP4.
- 4K missing: not all videos provide 4K, try 1440p/1080p.
- Playlist instead of single video: ensure the URL is a watch link or keep --no-playlist.
