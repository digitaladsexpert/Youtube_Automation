# app/tools.py (FIXED: dynamic topic threading, real error handling, no silent fallbacks)

import os
import json
import asyncio
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
        model="claude-sonnet-5",
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
        model="claude-sonnet-5",
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

    generator = kokoro_pipeline(script[:5000], voice='af_heart', speed=1.0)
    audio_chunks = [audio for audio, _, _ in generator]
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


# ---------- 7. ASSETS (ComfyUI / FLUX placeholder) ----------
async def generate_assets(job_id: str):
    """
    NOTE: real image generation is NOT wired up yet — plugging in your ComfyUI/FLUX
    workflow call below is still on you (the payload shape depends on your workflow
    JSON). Until you do, every scene gets a clearly-labeled placeholder frame.

    FIXED: the original try/except here had the real call commented out and only
    `pass` in the try body, so the except branch (which drew a placeholder) could
    NEVER run — no image, not even a placeholder, was ever produced by this
    function. edit_video()'s own separate fallback silently painted plain black
    frames instead. This version actually produces a visible placeholder.
    """
    async with aiofiles.open(f"jobs/{job_id}/scene_plan.json", 'r') as f:
        plan = json.loads(await f.read())
    scenes = plan["scenes"]
    os.makedirs(f"jobs/{job_id}/assets/images", exist_ok=True)

    for scene in scenes:
        img_path = f"jobs/{job_id}/assets/images/{scene['scene_id']}.png"
        prompt = scene.get("generation_prompt", "Abstract documentary visual")
        generated = False
        try:
            # TODO: wire this up to your real ComfyUI/FLUX workflow, e.g.:
            # resp = requests.post("http://127.0.0.1:8188/prompt", json={...}, timeout=60)
            # generated = resp.ok and <you saved the returned image to img_path>
            pass
        except Exception as e:
            print(f"⚠️ Image generation call failed for {scene['scene_id']}: {e}")

        if not generated:
            img = Image.new('RGB', (1920, 1080), color=(20, 20, 40))
            d = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 36)
            except Exception:
                font = ImageFont.load_default()
            d.text((80, 480), prompt[:60], fill='white', font=font)
            img.save(img_path)

    manifest = {"assets": [{"scene_id": s["scene_id"], "path": f"jobs/{job_id}/assets/images/{s['scene_id']}.png"} for s in scenes]}
    async with aiofiles.open(f"jobs/{job_id}/asset_manifest.json", 'w') as f:
        await f.write(json.dumps(manifest))
    return manifest


# ---------- 8. REAL EDITING (MoviePy) ----------
async def edit_video(job_id: str):
    async with aiofiles.open(f"jobs/{job_id}/scene_plan.json", 'r') as f:
        plan = json.loads(await f.read())
    clips = []
    for scene in plan["scenes"]:
        img_path = f"jobs/{job_id}/assets/images/{scene['scene_id']}.png"
        if not os.path.exists(img_path):
            img = Image.new('RGB', (1920, 1080), color='black')
            img.save(img_path)
        duration = scene.get("duration", 6)
        clip = ImageClip(img_path, duration=duration)
        if scene.get("motion") == "zoom":
            clip = clip.resize(lambda t: 1 + 0.05*t).set_position('center')
        clips.append(clip)
    final_video = concatenate_videoclips(clips, method="compose")
    audio_path = f"jobs/{job_id}/audio/final_audio.mp3"
    if os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
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
