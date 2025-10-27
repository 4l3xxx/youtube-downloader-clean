#!/usr/bin/env bash
set -euo pipefail

# Simple YouTube downloader (MP4 merged) for Linux/macOS
# Requires: yt-dlp and ffmpeg installed and in PATH

DL_DIR="${XDG_DOWNLOAD_DIR:-$HOME/Downloads}"
[[ -d "$DL_DIR" ]] || DL_DIR="$HOME/Downloads"

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "[Error] yt-dlp not found. Install it via your package manager." >&2
  echo "  macOS (brew):   brew install yt-dlp ffmpeg" >&2
  echo "  Ubuntu/Debian:  sudo apt-get install -y yt-dlp ffmpeg" >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[Warn] ffmpeg not found. Install ffmpeg for reliable merging/remux to MP4." >&2
fi

read -rp "YouTube URL: " URL
[[ -n "${URL}" ]] || { echo "No URL provided." >&2; exit 1; }

echo "Select quality target:";
echo " 1) 2160p (4K)";
echo " 2) 1440p (2K)";
echo " 3) 1080p";
echo " 4)  720p";
echo " 5)  480p";
echo " 6)  360p";
echo " 7)  240p";
echo " 8)  144p";
read -rp "Pick [1-8]: " CHOICE
case "${CHOICE}" in
  1) H=2160;; 2) H=1440;; 3) H=1080;; 4) H=720;;
  5) H=480;;  6) H=360;;  7) H=240;;  8) H=144;;
  *) echo "Invalid selection"; exit 1;;
esac

FMT="bv*[ext=mp4][height<=${H}]+ba[ext=m4a]/bv*[height<=${H}]+ba/b[ext=mp4][height<=${H}]/b[height<=${H}]"
OUTT="${DL_DIR}/%(title)s [%(resolution)s]-%(id)s.%(ext)s"

echo "Downloading to: ${DL_DIR}"
yt-dlp --no-playlist -f "$FMT" --remux-video mp4 --merge-output-format mp4 -o "$OUTT" "$URL"
echo "Done. Saved under: ${DL_DIR}"

