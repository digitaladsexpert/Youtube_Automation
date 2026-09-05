#!/usr/bin/env bash
set -e

echo "Checking system dependencies (ffmpeg, espeak-ng)..."
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v espeak-ng >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        echo "Installing via apt-get (needs sudo)..."
        sudo apt-get update && sudo apt-get install -y ffmpeg espeak-ng
    elif command -v brew >/dev/null 2>&1; then
        echo "Installing via Homebrew..."
        brew install ffmpeg espeak-ng
    else
        echo "Could not detect apt-get or brew. Install these manually:"
        echo "  ffmpeg:    https://ffmpeg.org/download.html"
        echo "  espeak-ng: https://github.com/espeak-ng/espeak-ng/releases"
    fi
else
    echo "ffmpeg and espeak-ng already found on PATH."
fi

echo "Creating Virtual Environment..."
python3 -m venv venv
source venv/bin/activate
echo "Installing Requirements..."
pip install --upgrade pip
pip install -r requirements.txt
echo "Setup Complete! Run: python run.py"
echo ""
echo "Optional: run ./setup_comfyui.sh separately if you want local image"
echo "generation (ComfyUI + FLUX) instead of the placeholder frames."
