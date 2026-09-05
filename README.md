# 🚀 YouTube Automation Production Pipeline (Native Python - No Docker)

## Features
- Topic-driven research, script, thumbnail, and metadata (previously hardcoded to one demo topic no matter what you sent)
- Dynamic 4-10 sec fast cuts
- Hard Policy Gate (No Profanity / No Financial Guarantees) + AI-disclosure auto-add
- Local TTS (Kokoro) + Captions (Whisper)
- Real human-review gate before delivery (approve/reject)
- Google Drive Auto-Upload

## Installation
1. Install Python 3.11+, FFmpeg, and **espeak-ng** (Kokoro TTS needs it as a system binary, not just a pip package — `apt-get install espeak-ng` / `brew install espeak-ng` / [Windows installer](https://github.com/espeak-ng/espeak-ng/releases)).
2. Run `setup.bat` (Windows) or `bash setup.sh` (Mac/Linux).
3. Add your `ANTHROPIC_API_KEY` in the `.env` file.
4. Put a Google Drive OAuth `credentials.json` in `secrets/` (see below).
5. Run `python run.py`.

## Trigger a video
```
curl -X POST "http://localhost:8000/start_job" -d "{\"topic\": \"Your Topic\"}"
```

## Check status
```
curl "http://localhost:8000/job/{job_id}/status"
```

## Human review gate
The pipeline now genuinely pauses in the `HUMAN_REVIEW` state once QC passes.
Move it forward or stop it:
```
curl -X POST "http://localhost:8000/job/{job_id}/approve"
curl -X POST "http://localhost:8000/job/{job_id}/reject"
```

## Google Drive setup (secrets/credentials.json)
1. Google Cloud Console → create/select a project → enable the **Google Drive API**.
2. Create an OAuth Client ID, type **Desktop app** → download the JSON → save it as `secrets/credentials.json`.
3. First delivery run opens a browser to authorize (`run_local_server`), then caches `secrets/token.pickle` for reuse.
4. **Headless server / Docker / RunPod etc.**: there's no browser there, so `run_local_server` can't complete the first auth. Do step 3 once on your own machine (with a browser), then copy the resulting `secrets/token.pickle` onto the server/into the container's `secrets/` folder (already volume-mounted in `docker-compose.yml`). It'll be reused/refreshed from there without ever needing a browser on the server itself.

## Model downloads (need internet on first run)
- Kokoro-82M weights pull from Hugging Face the first time `KPipeline()` initializes.
- Whisper's `base` model (~150MB) pulls from OpenAI's servers the first time `add_captions` runs.
- If your deployment box has restricted outbound access, allow: `en.wikipedia.org`, `api.anthropic.com`, `huggingface.co`, Whisper's model host, and `www.googleapis.com`/`oauth2.googleapis.com`.

## Still placeholder / needs your input
- **Image generation** (`app/tools.py: generate_assets`) — the ComfyUI/FLUX call is a stub with a `TODO`. Wire in your real workflow endpoint; until then every scene gets a labeled placeholder frame instead of a silent black one.
- **QC** (`app/tools.py: run_qc`) checks that the rendered file has audio and roughly matches the planned duration — it is not a real quality/content model.
- **Fact-checking** (`app/tools.py: fact_check_tool`) just confirms research produced non-empty facts — it doesn't independently verify anything.
- Postgres/pgvector and n8n were removed from `docker-compose.yml` since the app runs on SQLite and doesn't use n8n. Re-add them if you actually wire those in.
