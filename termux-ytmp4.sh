#!/data/data/com.termux/files/usr/bin/bash
set -e

# Minimal Termux YouTube downloader (about ~10 lines)
# Usage: ./termux-ytmp4.sh [URL] [HEIGHT]

url="$1"; [ -n "$url" ] || read -rp "YouTube URL: " url
q="${2:-1080}"
DL="$HOME/storage/downloads"; [ -d "$DL" ] || DL="/sdcard/Download"
FMT="bv*[ext=mp4][height<=${q}]+ba[ext=m4a]/bv*[height<=${q}]+ba/b[ext=mp4][height<=${q}]/b[height<=${q}]"
OUT="$DL/%(title)s [%(resolution)s]-%(id)s.%(ext)s"
yt-dlp --no-playlist -f "$FMT" --remux-video mp4 --merge-output-format mp4 -o "$OUT" "$url"
echo "Saved to: $DL"

