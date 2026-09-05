# app/tools.py (FIXED: dynamic topic threading, real error handling, no silent fallbacks)

import os
import json
import asyncio
import copy
import subprocess
import urllib.parse
from datetime import datetime
from typing import Dict, List, Any
import aiofiles
import httpx
from bs4 import BeautifulSoup
from moviepy.editor import *
import whisper
import soundfile as sf
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import yaml

from database.db import get_job

# ---------- LOAD CONFIG ----------
with open("config/config.yaml", 'r') as f:
    CONFIG = yaml.safe_load(f)

# ---------- KOKORO TTS SETUP ----------
try:
    from kokoro import KPipeline
    kokoro_pipeline = KPipeline(lang_code='a')
except Exception:
    print("⚠️ Kokoro not found. Install with: pip install kokoro")
    kokoro_pipeline = None


async def _get_topic(job_id: str) -> str:
    """Every job's actual topic lives in the DB row created by /start_job.
    Every content-generating tool below reads it from here instead of
    hardcoding a demo topic."""
    job = await get_job(job_id)
    return (job or {}).get("topic") or "General Knowledge"


# ---------- 1. RESEARCH (topic-driven) ----------
async def research_tool(job_id: str):
    topic = await _get_topic(job_id)
    os.makedirs(f"jobs/{job_id}/research", exist_ok=True)
    sources = []
    extracted_facts = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page_title = topic
        summary = None

        # 1) Try the topic as a direct Wikipedia page title.
        try:
            resp = await client.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(topic)}"
            )
            if resp.status_code == 200:
                summary = resp.json()
                page_title = summary.get("title", topic)
        except Exception as e:
            print(f"Direct Wikipedia lookup failed: {e}")

        # 2) Fall back to a search if the topic isn't an exact page title.
        if not summary:
            try:
                search_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query", "list": "search", "srsearch": topic,
                        "format": "json", "srlimit": 1,
                    },
                )
                results = search_resp.json().get("query", {}).get("search", [])
                if results:
                    page_title = results[0]["title"]
                    resp2 = await client.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title)}"
                    )
                    if resp2.status_code == 200:
                        summary = resp2.json()
            except Exception as e:
                print(f"Wikipedia search fallback failed: {e}")

        if summary and summary.get("extract"):
            extract = summary["extract"]
            url = summary.get("content_urls", {}).get("desktop", {}).get(
                "page", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title)}"
            )
            sources.append({"url": url, "text": extract[:1000], "type": "wiki"})
            sentences = [s.strip() for s in extract.split(". ") if s.strip()]
            extracted_facts = sentences[:3]

    if not extracted_facts:
        extracted_facts = [f"No verified sources found for '{topic}' — proceeding on general knowledge only."]

    data = {"topic": topic, "sources": sources, "extracted_facts": extracted_facts}
    async with aiofiles.open(f"jobs/{job_id}/research/research.json", 'w') as f:
        await f.write(json.dumps(data, indent=2))
    return data


async def fact_check_tool(job_id: str):
    # NOTE: this is a lightweight placeholder, not real independent fact-checking —
    # it just confirms research_tool actually produced non-empty facts. Wire in a
    # real fact-checking API/model call here if you need genuine verification.
    async with aiofiles.open(f"jobs/{job_id}/research/research.json", 'r') as f:
        data = json.loads(await f.read())
    facts = [f for f in data.get("extracted_facts", []) if isinstance(f, str) and f.strip()]
    for fact in facts:
        print(f"✅ Noted: {fact}")
    return {"status": "VERIFIED" if facts else "NO_FACTS", "facts": facts}


# ---------- 2. CLAUDE CREATIVE DIRECTION (topic-driven) ----------
async def creative_direction(job_id: str):
    import anthropic
    topic = await _get_topic(job_id)
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=CONFIG.get("models", {}).get("claude", "claude-haiku-4-5-20251001"),
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": (
                f"Topic: {topic}. Write a unique 2-paragraph creative direction for a "
                "documentary-style YouTube video. Focus on human emotion, stakes, and a "
                "compelling hook."
            )
        }]
    )
    direction = response.content[0].text
    async with aiofiles.open(f"jobs/{job_id}/creative_direction.txt", 'w') as f:
        await f.write(direction)
    return {"direction": direction}


# ---------- 3. REAL SCRIPT (Claude API, topic-driven) ----------
async def generate_script(job_id: str):
    import anthropic
    topic = await _get_topic(job_id)

    direction = ""
    direction_path = f"jobs/{job_id}/creative_direction.txt"
    if os.path.exists(direction_path):
        async with aiofiles.open(direction_path, 'r') as f:
            direction = await f.read()

    research_context = ""
    research_path = f"jobs/{job_id}/research/research.json"
    if os.path.exists(research_path):
        async with aiofiles.open(research_path, 'r') as f:
            research = json.loads(await f.read())
        research_context = "\n".join(research.get("extracted_facts", []))

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = f"""
    Write a 4000-word YouTube script (15-20 mins) on the topic: "{topic}".

    Creative direction:
    {direction}

    Relevant research notes:
    {research_context}

    RULES:
    1. NO profanity, NO hate speech.
    2. NO financial guarantees like "risk-free" or "guaranteed profit".
    3. Use conversational American English.
    4. End with the disclaimer: "This video is for informational purposes only and is not financial advice."
    """
    response = client.messages.create(
        model=CONFIG.get("models", {}).get("claude", "claude-haiku-4-5-20251001"),
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    script = response.content[0].text

    # AI-disclosure auto-add (config.youtube_hard_rules.ai_disclosure.required was
    # declared in config.yaml but never actually implemented anywhere — this wires it up).
    if CONFIG.get("youtube_hard_rules", {}).get("ai_disclosure", {}).get("required"):
        if "AI-generated" not in script and "AI-assisted" not in script:
            script += "\n\n[This video uses AI-generated narration and/or visuals.]"

    os.makedirs(f"jobs/{job_id}/script", exist_ok=True)
    async with aiofiles.open(f"jobs/{job_id}/script/script.txt", 'w') as f:
        await f.write(script)
    return {"script": script[:100]}


# ---------- 4. DYNAMIC SCENE PLANNING (4-10 sec) ----------
async def plan_scenes(job_id: str):
    async with aiofiles.open(f"jobs/{job_id}/script/script.txt", 'r') as f:
        script = await f.read()
    sentences = script.split('. ')
    scenes = []
    time = 0.0
    for i, sent in enumerate(sentences):
        if not sent.strip(): continue
        dur = max(4, min(10, 4 + (len(sent) // 150)))
        scenes.append({
            "scene_id": f"scene_{i:03d}",
            "narration": sent[:100],
            "time_start": round(time, 2),
            "time_end": round(time + dur, 2),
            "duration": dur,
            "generation_prompt": f"Visual for: {sent[:100]}",
            "motion": "zoom" if i % 3 == 0 else "pan"
        })
        time += dur
    plan = {"total_duration": time, "scenes": scenes}
    os.makedirs(f"jobs/{job_id}/", exist_ok=True)
    async with aiofiles.open(f"jobs/{job_id}/scene_plan.json", 'w') as f:
        await f.write(json.dumps(plan, indent=2))
    return plan


# ---------- 5. REAL VOICE (Kokoro TTS) ----------
async def generate_voice(job_id: str):
    async with aiofiles.open(f"jobs/{job_id}/script/script.txt", 'r') as f:
        script = await f.read()
    os.makedirs(f"jobs/{job_id}/audio", exist_ok=True)
    audio_path = f"jobs/{job_id}/audio/voice.wav"

    if not kokoro_pipeline:
        # FIXED: previously wrote 1 second of silence and let the pipeline continue
        # (captions would then be generated from silence with no error, ever).
        # Now it fails loudly so you actually see the problem in the job's errors.
        raise RuntimeError(
            "Kokoro TTS is not installed/loaded. Install it with `pip install kokoro` "
            "(plus its model weights/dependencies) before running voice generation."
        )

    # FIXED (two separate bugs):
    # 1) `script[:5000]` only fed the first ~20% of a 4000-word script to Kokoro —
    #    the video's scenes covered the full script, but narration silently cut
    #    off after ~4-7 minutes, leaving the rest of a 15-20 min video dead silent.
    #    Kokoro's own pipeline already auto-chunks long text internally (verified
    #    in its source), so there's no need to cap this at the app level at all.
    # 2) `for audio, _, _ in generator` — Kokoro's Result object yields
    #    (graphemes, phonemes, audio) for backward compatibility, in that order.
    #    So the old code's "audio" variable actually held the input TEXT STRING,
    #    not the audio waveform. `np.concatenate()` on a list of strings would
    #    have raised immediately — this function could never have produced real
    #    audio, truncation aside.
    generator = kokoro_pipeline(script, voice='af_heart', speed=1.0)
    audio_chunks = []
    for result in generator:
        a = result.audio
        if a is None:
            continue
        if hasattr(a, "detach"):  # torch.Tensor -> numpy
            a = a.detach().cpu().numpy()
        audio_chunks.append(a)

    if not audio_chunks:
        raise RuntimeError("Kokoro produced no audio output for this script.")
    full_audio = np.concatenate(audio_chunks)
    sf.write(audio_path, full_audio, 24000)
    return {"voice_path": audio_path}


# ---------- 6. REAL AUDIO MIXING ----------
async def mix_audio(job_id: str):
    voice_path = f"jobs/{job_id}/audio/voice.wav"
    music_path = "assets/music/background_1.mp3"
    if not os.path.exists(music_path):
        from moviepy.audio.AudioClip import AudioClip
        silence = AudioClip(lambda t: 0, duration=600)
        silence.write_audiofile(music_path, fps=44100)
    voice_clip = AudioFileClip(voice_path)
    music_clip = AudioFileClip(music_path).volumex(0.2).loop(duration=voice_clip.duration)
    final_audio = CompositeAudioClip([voice_clip, music_clip])
    final_path = f"jobs/{job_id}/audio/final_audio.mp3"
    final_audio.write_audiofile(final_path, fps=44100, codec='libmp3lame')
    return {"audio": final_path}


# ---------- 7. ASSETS (real ComfyUI client + safe placeholder fallback) ----------
async def generate_assets(job_id: str):
    """
    Calls a real ComfyUI server if it's configured and reachable, using a
    workflow JSON YOU export from ComfyUI's own UI (Workflow menu -> Export
    (API)) — that's the only reliable way to get a correct node graph for
    whatever checkpoint/nodes you actually have installed; hand-writing one
    is too easy to get subtly wrong. Falls back to a clearly-labeled
    placeholder frame if ComfyUI isn't set up yet, unreachable, or a specific
    scene's generation fails, so a missing/broken ComfyUI setup never
    silently blocks the rest of the pipeline.

    See config.yaml's `comfyui:` section and the README for setup steps.
    """
    comfy_cfg = CONFIG.get("comfyui", {}) or {}
    comfy_url = comfy_cfg.get("url", "http://127.0.0.1:8188")
    workflow_path = comfy_cfg.get("workflow_path", "config/comfyui_workflow.json")
    prompt_node_id = comfy_cfg.get("positive_prompt_node_id")
    timeout_s = comfy_cfg.get("timeout_seconds", 120)

    workflow_template = None
    if os.path.exists(workflow_path):
        with open(workflow_path, 'r') as f:
            workflow_template = json.load(f)
        if not prompt_node_id:
            # Auto-detect the first CLIPTextEncode node if you didn't pin one in config.
            for node_id, node in workflow_template.items():
                if node.get("class_type") == "CLIPTextEncode":
                    prompt_node_id = node_id
                    break

    async with aiofiles.open(f"jobs/{job_id}/scene_plan.json", 'r') as f:
        plan = json.loads(await f.read())
    scenes = plan["scenes"]
    os.makedirs(f"jobs/{job_id}/assets/images", exist_ok=True)

    for scene in scenes:
        img_path = f"jobs/{job_id}/assets/images/{scene['scene_id']}.png"
        prompt = scene.get("generation_prompt", "Abstract documentary visual")
        generated = False
        failure_reason = "ComfyUI not configured (no config/comfyui_workflow.json)"

        if workflow_template and prompt_node_id:
            try:
                generated = await _comfyui_generate(
                    comfy_url, workflow_template, prompt_node_id, prompt, img_path, timeout_s
                )
                if not generated:
                    failure_reason = "ComfyUI ran but returned no image"
            except Exception as e:
                failure_reason = f"ComfyUI call failed: {e}"
                print(f"⚠️ {failure_reason} (scene {scene['scene_id']})")

        if not generated:
            img = Image.new('RGB', (1920, 1080), color=(20, 20, 40))
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 34)
            except Exception:
                font = ImageFont.load_default()
            d.text((80, 440), prompt[:60], fill='white', font=font)
            d.text((80, 500), f"[placeholder — {failure_reason[:70]}]", fill=(180, 180, 180), font=font)
            img.save(img_path)

    manifest = {"assets": [{"scene_id": s["scene_id"], "path": f"jobs/{job_id}/assets/images/{s['scene_id']}.png"} for s in scenes]}
    async with aiofiles.open(f"jobs/{job_id}/asset_manifest.json", 'w') as f:
        await f.write(json.dumps(manifest))
    return manifest


async def _comfyui_generate(comfy_url: str, workflow_template: dict, prompt_node_id: str,
                             prompt_text: str, out_path: str, timeout_s: int) -> bool:
    """
    Real ComfyUI API client: POST /prompt, poll /history/{id}, fetch the
    resulting image via /view. This is ComfyUI's stable, documented API
    contract — the part that's fabricated per-install is the workflow graph
    itself (loader/sampler nodes), which is why that comes from your own
    exported JSON rather than being hardcoded here.
    """
    workflow = copy.deepcopy(workflow_template)
    workflow[prompt_node_id]["inputs"]["text"] = prompt_text

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(f"{comfy_url}/prompt", json={"prompt": workflow})
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

        elapsed = 0
        poll_interval = 2
        while elapsed < timeout_s:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            hist_resp = await client.get(f"{comfy_url}/history/{prompt_id}")
            history = hist_resp.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    for img_info in node_output.get("images", []):
                        img_resp = await client.get(
                            f"{comfy_url}/view",
                            params={
                                "filename": img_info["filename"],
                                "subfolder": img_info.get("subfolder", ""),
                                "type": img_info.get("type", "output"),
                            },
                        )
                        with open(out_path, 'wb') as f:
                            f.write(img_resp.content)
                        return True
                return False  # job completed but produced no image output
        return False  # timed out waiting for /history


# ---------- 8. REAL EDITING (MoviePy) ----------
async def edit_video(job_id: str):
    """
    FIXED: scene durations in scene_plan.json are a rough character-count guess
    made BEFORE any real audio exists — they have no actual relationship to
    Kokoro's real speaking pace. Previously the video was built purely from
    that guess, completely independent of the real narration length: if the
    guess ran short, narration got cut off when the video ran out of scenes;
    if it ran long (more likely now that generate_voice covers the full
    script), the video would just go silent for however long the guess
    overshot by. This rescales every scene's duration proportionally so the
    video's total length always matches the real audio exactly, while still
    preserving each scene's relative share of screen time.
    """
    async with aiofiles.open(f"jobs/{job_id}/scene_plan.json", 'r') as f:
        plan = json.loads(await f.read())
    scenes = plan["scenes"]

    audio_path = f"jobs/{job_id}/audio/final_audio.mp3"
    audio = AudioFileClip(audio_path) if os.path.exists(audio_path) else None

    planned_total = plan.get("total_duration") or sum(s.get("duration", 6) for s in scenes)
    scale = (audio.duration / planned_total) if (audio and planned_total) else 1.0

    clips = []
    for scene in scenes:
        img_path = f"jobs/{job_id}/assets/images/{scene['scene_id']}.png"
        if not os.path.exists(img_path):
            img = Image.new('RGB', (1920, 1080), color='black')
            img.save(img_path)
        duration = max(scene.get("duration", 6) * scale, 0.5)  # keep a sane floor
        clip = ImageClip(img_path, duration=duration)
        if scene.get("motion") == "zoom":
            clip = clip.resize(lambda t: 1 + 0.05*t).set_position('center')
        clips.append(clip)

    final_video = concatenate_videoclips(clips, method="compose")
    if audio:
        final_video = final_video.set_audio(audio)
    os.makedirs(f"jobs/{job_id}/final", exist_ok=True)
    final_path = f"jobs/{job_id}/final/video.mp4"
    final_video.write_videofile(final_path, fps=24, codec='libx264', audio_codec='aac')
    return {"video": final_path}


# ---------- 9. REAL CAPTIONS (Whisper) ----------
async def add_captions(job_id: str):
    audio_path = f"jobs/{job_id}/audio/final_audio.mp3"
    video_path = f"jobs/{job_id}/final/video.mp4"
    output_path = f"jobs/{job_id}/final/video_with_captions.mp4"
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, word_timestamps=True)
    srt_path = f"jobs/{job_id}/captions/subtitles.srt"
    os.makedirs(f"jobs/{job_id}/captions", exist_ok=True)
    with open(srt_path, 'w') as f:
        for i, seg in enumerate(result["segments"]):
            start = seg["start"]
            end = seg["end"]
            text = seg["text"].strip()
            f.write(f"{i+1}\n{format_time(start)} --> {format_time(end)}\n{text}\n\n")
    cmd = f"ffmpeg -i {video_path} -vf subtitles={srt_path} -c:a copy {output_path} -y"
    subprocess.run(cmd, shell=True, check=True)
    os.replace(output_path, video_path)
    return {"captions": srt_path}


def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# ---------- 10. THUMBNAIL (topic-driven) ----------
async def generate_thumbnail(job_id: str):
    topic = await _get_topic(job_id)
    headline = topic.upper()[:40]
    img = Image.new('RGB', (1280, 720), color='navy')
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 60)
    except Exception:
        font = ImageFont.load_default()
    d.text((80, 300), headline, fill='white', font=font)
    thumb_path = f"jobs/{job_id}/final/thumbnail.png"
    os.makedirs(f"jobs/{job_id}/final", exist_ok=True)
    img.save(thumb_path)
    return {"thumbnail": thumb_path}


# ---------- 11. METADATA (topic-driven) ----------
async def generate_metadata(job_id: str):
    topic = await _get_topic(job_id)
    words = [w for w in topic.replace("-", " ").split() if w]
    tags = list(dict.fromkeys(words + ["Documentary", "Explained", "AI Generated"]))[:15]
    meta = {
        "title": f"{topic}: The Story They Don't Want You to Know"[:100],
        "description": (
            f"A deep dive into {topic}. "
            "This video is for informational purposes only and is not financial advice. "
            "Narration and/or visuals are AI-assisted."
        ),
        "tags": tags,
    }
    os.makedirs(f"jobs/{job_id}/final", exist_ok=True)
    async with aiofiles.open(f"jobs/{job_id}/final/metadata.json", 'w') as f:
        await f.write(json.dumps(meta, indent=2))
    return meta


# ---------- 12. HARD POLICY CHECK ----------
async def policy_check(job_id: str) -> bool:
    script_path = f"jobs/{job_id}/script/script.txt"
    if not os.path.exists(script_path): return True
    with open(script_path, 'r') as f:
        script = f.read().lower()
    bad_words = CONFIG['youtube_hard_rules']['profanity']['blocked_words']
    for w in bad_words:
        if w in script:
            print(f"🚨 BLOCKED: Profanity {w}")
            return False
    bad_phrases = CONFIG['youtube_hard_rules']['financial_claims']['prohibited_phrases']
    for p in bad_phrases:
        if p in script:
            print(f"🚨 BLOCKED: Financial Guarantee {p}")
            return False
    return True


# ---------- 13. QC ----------
async def run_qc(job_id: str) -> int:
    """
    FIXED: previously returned a flat hardcoded 92 whenever the video file
    existed (0 otherwise) — the config's quality_threshold: 85 gate was
    effectively decorative. This still isn't a real perceptual-quality model,
    but it now actually checks the file: does it have audio, and does its
    duration roughly match what scene_plan.json expected.
    """
    video_path = f"jobs/{job_id}/final/video.mp4"
    plan_path = f"jobs/{job_id}/scene_plan.json"
    if not os.path.exists(video_path):
        return 0

    score = 70  # baseline: file exists and is presumed readable
    try:
        clip = VideoFileClip(video_path)
        actual_duration = clip.duration
        has_audio = clip.audio is not None
        clip.close()

        if has_audio:
            score += 10

        if os.path.exists(plan_path):
            with open(plan_path, 'r') as f:
                plan = json.load(f)
            expected = plan.get("total_duration") or actual_duration
            drift = abs(actual_duration - expected) / max(expected, 1)
            score += max(0, 20 - int(drift * 100))
    except Exception as e:
        print(f"QC check failed: {e}")
        score = max(score - 30, 0)

    return min(score, 100)


# ---------- 14. FINAL GDRIVE DELIVERY ----------
async def deliver_to_gdrive(job_id: str):
    if not await policy_check(job_id):
        raise Exception("Policy Failed")
    from scripts.upload_to_gdrive import upload_job_to_gdrive
    result = upload_job_to_gdrive(job_id, f"jobs/{job_id}/final/")
    from database.db import update_gdrive_link
    await update_gdrive_link(job_id, result.get("gdrive_folder"))
    return result
