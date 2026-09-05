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

# For downloading the model files below (verified real CLI, from
# huggingface_hub's own source — the older `huggingface-cli` name still works
# too, this is just the current one).
./venv/bin/pip install -U huggingface_hub

echo ""
echo "==================================================================="
echo "ComfyUI installed at $(pwd)"
echo ""
echo "Start it with:"
echo "  cd $(pwd) && ./venv/bin/python main.py --listen 0.0.0.0 --port 8188"
echo ""
echo "Now get the FLUX model files (10-25GB+ combined — I can't verify the"
echo "CURRENT exact repo names/filenames live from this sandbox since"
echo "huggingface.co isn't reachable from here, so double-check these against"
echo "the model's page before running. FLUX.1-schnell is Apache-2.0, no HF"
echo "login needed; FLUX.1-dev needs you to accept a license on huggingface.co"
echo "first, then pass --token <your_hf_token> to the commands below):"
echo ""
echo "  cd $(pwd)"
echo "  ./venv/bin/hf download black-forest-labs/FLUX.1-schnell flux1-schnell.safetensors --local-dir models/unet"
echo "  ./venv/bin/hf download comfyanonymous/flux_text_encoders clip_l.safetensors t5xxl_fp16.safetensors --local-dir models/clip"
echo "  ./venv/bin/hf download black-forest-labs/FLUX.1-schnell ae.safetensors --local-dir models/vae"
echo ""
echo "  (older huggingface_hub versions: swap 'hf download' for 'huggingface-cli download' above)"
echo ""
echo "Then in ComfyUI's web UI (http://localhost:8188), build a Text-to-Image"
echo "FLUX workflow (UNETLoader -> DualCLIPLoader -> VAELoader -> CLIPTextEncode"
echo "-> KSampler -> VAEDecode -> SaveImage — these are the real node types from"
echo "ComfyUI's own official Flux blueprint), then Workflow menu -> Export (API)"
echo "and save it as config/comfyui_workflow.json back in the main project folder."
echo "==================================================================="
