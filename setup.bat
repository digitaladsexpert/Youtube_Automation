@echo off
echo Checking for ffmpeg and espeak-ng...

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo ffmpeg not found on PATH. Trying winget...
    where winget >nul 2>nul
    if %errorlevel% equ 0 (
        winget install --id Gyan.FFmpeg -e --silent
    )
    echo If ffmpeg is still not on PATH after this, install manually:
    echo https://ffmpeg.org/download.html
)

where espeak-ng >nul 2>nul
if %errorlevel% neq 0 (
    echo espeak-ng not found on PATH. Kokoro TTS needs it as a system binary.
    echo Download + run the installer, then add its folder to PATH:
    echo https://github.com/espeak-ng/espeak-ng/releases
)

echo Creating Virtual Environment...
python -m venv venv
call venv\Scripts\activate.bat
echo Installing Requirements...
pip install --upgrade pip
pip install -r requirements.txt
echo Setup Complete! Run: python run.py
echo.
echo Optional: run setup_comfyui.bat separately if you want local image
echo generation (ComfyUI + FLUX) instead of the placeholder frames.
pause
