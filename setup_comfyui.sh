#!/usr/bin/env bash
set -e

# Installs ComfyUI as a SEPARATE app in its own venv (sibling to this project,
# not inside it) — that's the standard/recommended way to run it, and keeps
# its dependency pins from ever conflicting with this pipeline's own venv.
# Verified against ComfyUI's real requirements.txt (github.com/comfyanonymous/ComfyUI)
# at the time this script was written — transformers>=4.50.3, numpy>=1.25.0 etc.
# are all loose/compatible with this project's pins, so no conflict either way,
# but a separate venv is still the safer, standard setup.

cd ..
if [ -d "ComfyUI" ]; then
    echo "ComfyUI/ already exists here — skipping clone, just reinstalling deps."
else
    git clone https://github.com/comfyanonymous/ComfyUI.git
fi

cd ComfyUI
python3 -m venv venv
./venv/bin/pip install --upgrade pip

# Default install pulls the GPU (CUDA) build of torch. If you're on a machine
# with no NVIDIA GPU, comment the next line and uncomment the CPU one instead.
./venv/bin/pip install -r requirements.txt
# ./venv/bin/pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

echo ""
echo "==================================================================="
echo "ComfyUI installed at $(pwd)"
echo ""
echo "Start it with:"
echo "  cd $(pwd) && ./venv/bin/python main.py --listen 0.0.0.0 --port 8188"
echo ""
echo "You still need FLUX model files (not downloaded by this script —"
echo "10-25GB+ combined, and I can't verify exact current filenames/links"
echo "live from here, so check the model's Hugging Face page):"
echo "  models/unet/flux1-schnell.safetensors   (Apache-2.0, no HF login needed)"
echo "    or flux1-dev.safetensors              (better quality, needs HF license accept)"
echo "  models/clip/clip_l.safetensors"
echo "  models/clip/t5xxl_fp16.safetensors"
echo "  models/vae/ae.safetensors"
echo ""
echo "Then in ComfyUI's web UI (http://localhost:8188), build a Text-to-Image"
echo "FLUX workflow (UNETLoader -> DualCLIPLoader -> VAELoader -> CLIPTextEncode"
echo "-> KSampler -> VAEDecode -> SaveImage — these are the real node types from"
echo "ComfyUI's own official Flux blueprint), then Workflow menu -> Export (API)"
echo "and save it as config/comfyui_workflow.json back in the main project folder."
echo "==================================================================="
