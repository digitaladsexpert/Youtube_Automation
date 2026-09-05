@echo off
REM Installs ComfyUI as a SEPARATE app in its own venv (sibling to this
REM project, not inside it). Verified against ComfyUI's real requirements.txt
REM (github.com/comfyanonymous/ComfyUI) at the time this script was written.

cd ..
if exist ComfyUI (
    echo ComfyUI folder already exists here - skipping clone, just reinstalling deps.
) else (
    git clone https://github.com/comfyanonymous/ComfyUI.git
)

cd ComfyUI
python -m venv venv
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
REM Default pulls the GPU (CUDA) torch build. No NVIDIA GPU? Comment the line
REM above and use instead:
REM pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

echo.
echo ===================================================================
echo ComfyUI installed.
echo.
echo Start it with:
echo   cd ComfyUI ^&^& venv\Scripts\python main.py --listen 0.0.0.0 --port 8188
echo.
echo You still need FLUX model files (not downloaded by this script -
echo 10-25GB+ combined, check the model's Hugging Face page for current
echo filenames/links):
echo   models\unet\flux1-schnell.safetensors   (Apache-2.0, no HF login needed)
echo     or flux1-dev.safetensors              (better quality, needs HF license accept)
echo   models\clip\clip_l.safetensors
echo   models\clip\t5xxl_fp16.safetensors
echo   models\vae\ae.safetensors
echo.
echo Then in ComfyUI's web UI (http://localhost:8188), build a Text-to-Image
echo FLUX workflow (UNETLoader -^> DualCLIPLoader -^> VAELoader -^> CLIPTextEncode
echo -^> KSampler -^> VAEDecode -^> SaveImage - these are the real node types from
echo ComfyUI's own official Flux blueprint), then Workflow menu -^> Export (API)
echo and save it as config\comfyui_workflow.json back in the main project folder.
echo ===================================================================
pause
