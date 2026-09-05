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
pip install -U huggingface_hub

echo.
echo ===================================================================
echo ComfyUI installed.
echo.
echo Start it with:
echo   cd ComfyUI ^&^& venv\Scripts\python main.py --listen 0.0.0.0 --port 8188
echo.
echo Now get the FLUX model files (10-25GB+ combined - I can't verify the
echo CURRENT exact repo names/filenames live from this sandbox since
echo huggingface.co isn't reachable from here, so double-check these against
echo the model's page before running. FLUX.1-schnell is Apache-2.0, no HF
echo login needed; FLUX.1-dev needs you to accept a license on huggingface.co
echo first, then pass --token your_hf_token to the commands below):
echo.
echo   hf download black-forest-labs/FLUX.1-schnell flux1-schnell.safetensors --local-dir models\unet
echo   hf download comfyanonymous/flux_text_encoders clip_l.safetensors t5xxl_fp16.safetensors --local-dir models\clip
echo   hf download black-forest-labs/FLUX.1-schnell ae.safetensors --local-dir models\vae
echo.
echo   (older huggingface_hub versions: swap "hf download" for "huggingface-cli download" above)
echo.
echo Then in ComfyUI's web UI (http://localhost:8188), build a Text-to-Image
echo FLUX workflow (UNETLoader -^> DualCLIPLoader -^> VAELoader -^> CLIPTextEncode
echo -^> KSampler -^> VAEDecode -^> SaveImage - these are the real node types from
echo ComfyUI's own official Flux blueprint), then Workflow menu -^> Export (API)
echo and save it as config\comfyui_workflow.json back in the main project folder.
echo ===================================================================
pause
