@echo off
setlocal enabledelayedexpansion

REM --- Simple YouTube downloader (MP4 merged) ---
REM Requirements: yt-dlp.exe and ffmpeg.exe in PATH or same folder

set "DL_DIR=%USERPROFILE%\Downloads"
if not exist "%DL_DIR%" (
  echo [Warn] Downloads folder not found at "%DL_DIR%". Using current directory.
  set "DL_DIR=%CD%"
)

where yt-dlp >nul 2>&1 || (
  echo [Error] yt-dlp not found in PATH.
  echo - Get yt-dlp.exe: https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
  echo - Put yt-dlp.exe in the same folder as this script or in PATH.
  exit /b 1
)
where ffmpeg >nul 2>&1 || (
  echo [Warn] ffmpeg not found. Install ffmpeg for reliable merging/remux to MP4.
)

echo Enter YouTube URL:
set /p "URL=> "
if "%URL%"=="" (
  echo No URL provided. Exiting.
  exit /b 1
)

echo.
echo Choose quality target:
echo  1^) 2160p (4K)
echo  2^) 1440p (2K)
echo  3^) 1080p
echo  4^)  720p
echo  5^)  480p
echo  6^)  360p
echo  7^)  240p
echo  8^)  144p
set /p "CHOICE=Select [1-8]: "

set "H="
if "%CHOICE%"=="1" set "H=2160"
if "%CHOICE%"=="2" set "H=1440"
if "%CHOICE%"=="3" set "H=1080"
if "%CHOICE%"=="4" set "H=720"
if "%CHOICE%"=="5" set "H=480"
if "%CHOICE%"=="6" set "H=360"
if "%CHOICE%"=="7" set "H=240"
if "%CHOICE%"=="8" set "H=144"
if "%H%"=="" (
  echo Invalid selection.
  exit /b 1
)

set "FMT=bv*[ext=mp4][height<=%H%]+ba[ext=m4a]/bv*[height<=%H%]+ba/b[ext=mp4][height<=%H%]/b[height<=%H%]"
set "OUTT=%DL_DIR%\%%(title)s [%%(resolution)s]-%%(id)s.%%(ext)s"

echo.
echo Downloading to: "%DL_DIR%"
echo Please wait...
yt-dlp --no-playlist -f "%FMT%" --remux-video mp4 --merge-output-format mp4 -o "%OUTT" "%URL%"
set "ERR=%ERRORLEVEL%"
if %ERR% neq 0 (
  echo Download failed with exit code %ERR%.
  exit /b %ERR%
)

echo.
echo Done. Opening Downloads folder...
start "" "%DL_DIR%"
exit /b 0

