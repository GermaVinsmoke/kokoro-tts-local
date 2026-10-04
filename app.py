"""Local Kokoro text-to-speech server."""

from functools import lru_cache
from pathlib import Path
import re
import subprocess
from threading import Lock

import imageio_ffmpeg
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Kokoro Local")
STATIC = Path(__file__).resolve().parent / "static"
SAMPLE_RATE = 24000
BREAK_TAG = re.compile(r"<break\b[^>]*>")
VALID_BREAK = re.compile(r'''<break\s+time\s*=\s*["'](\d+(?:\.\d+)?|\.\d+)s["']\s*/>''')

# Kokoro voice prefixes indicate the language used by KPipeline.
VOICES = {
    "American English": [
        ("af_heart", "Heart · feminine"),
        ("af_bella", "Bella · feminine"),
        ("af_nicole", "Nicole · feminine"),
        ("af_sarah", "Sarah · feminine"),
        ("af_sky", "Sky · feminine"),
        ("am_adam", "Adam · masculine"),
        ("am_michael", "Michael · masculine"),
        ("am_echo", "Echo · masculine"),
    ],
    "British English": [
        ("bf_emma", "Emma · feminine"),
        ("bf_isabella", "Isabella · feminine"),
        ("bm_george", "George · masculine"),
        ("bm_lewis", "Lewis · masculine"),
    ],
}
VOICE_CODES = {code for group in VOICES.values() for code, _ in group}
# Model synthesis and lazy pipeline loading happen one request at a time.
synthesis_lock = Lock()


class GenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice: str = "af_heart"
    speed: float = Field(default=1.0, ge=0.5, le=2.0, allow_inf_nan=False)


@lru_cache(maxsize=2)
def get_pipeline(language: str):
    from kokoro import KPipeline

    return KPipeline(lang_code=language)


def parse_segments(text: str) -> list[str | float]:
    """Split speech and explicit pauses; reject malformed break tags."""
    segments = []
    cursor = 0
    total_pause = 0.0
    for match in BREAK_TAG.finditer(text):
        speech = text[cursor:match.start()]
        if re.search(r"<break\b", speech):
            raise ValueError('Invalid break tag. Use <break time="0.2s" />.')
        if speech.strip():
            segments.append(speech.strip())
        valid = VALID_BREAK.fullmatch(match.group())
        if not valid:
            raise ValueError('Invalid break tag. Use <break time="0.2s" />.')
        seconds = float(valid.group(1))
        if seconds <= 0 or seconds > 10:
            raise ValueError("Each break must be greater than 0 and at most 10 seconds.")
        total_pause += seconds
        if total_pause > 60 or sum(isinstance(item, float) for item in segments) >= 50:
            raise ValueError("Use at most 50 breaks and 60 seconds of total silence.")
        segments.append(seconds)
        cursor = match.end()
    trailing = text[cursor:]
    if re.search(r"<break\b", trailing):
        raise ValueError('Invalid break tag. Use <break time="0.2s" />.')
    if trailing.strip():
        segments.append(trailing.strip())
    if not any(isinstance(item, str) for item in segments):
        raise ValueError("Enter some text to speak, not only break tags.")
    return segments


def synthesize(text: str, voice: str, speed: float = 1.0, segments: list[str | float] | None = None) -> bytes:
    if segments is None:
        segments = parse_segments(text)
    language = voice[0]  # a = American English, b = British English
    chunks = []
    has_speech = False
    with synthesis_lock:
        pipeline = get_pipeline(language)
        for segment in segments:
            if isinstance(segment, float):
                chunks.append(np.zeros(round(segment * SAMPLE_RATE), dtype=np.float32))
                continue
            for _, _, audio in pipeline(segment, voice=voice, speed=speed):
                if audio is not None:
                    if hasattr(audio, "detach"):
                        audio = audio.detach().cpu().numpy()
                    chunk = np.asarray(audio, dtype=np.float32).reshape(-1)
                    if chunk.size:
                        chunks.append(chunk)
                        has_speech = True

    if not has_speech:
        raise ValueError("Kokoro did not produce any audio. Try different text.")

    samples = np.concatenate(chunks)
    # imageio-ffmpeg supplies its own executable, so a separate ffmpeg install
    # is not required. Kokoro outputs mono audio at 24 kHz.
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner", "-loglevel", "error",
        "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "pipe:0",
        "-codec:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", "pipe:1",
    ]
    result = subprocess.run(command, input=samples.tobytes(), capture_output=True, check=False)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"MP3 encoding failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/styles.css")
def styles():
    return FileResponse(STATIC / "styles.css", media_type="text/css")


@app.get("/app.js")
def script():
    return FileResponse(STATIC / "app.js", media_type="text/javascript")


@app.get("/api/voices")
def voices():
    return [{"group": group, "voices": [{"id": code, "name": label} for code, label in items]}
            for group, items in VOICES.items()]


@app.post("/api/generate")
def generate(request: GenerateRequest):
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="Enter some text to convert.")
    if request.voice not in VOICE_CODES:
        raise HTTPException(status_code=422, detail="Select a valid voice.")
    try:
        segments = parse_segments(request.text.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        mp3 = synthesize(request.text.strip(), request.voice, request.speed, segments)
    except Exception as exc:
        # Show useful local setup / model download errors in the browser.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=mp3, media_type="audio/mpeg",
                    headers={"Content-Disposition": 'attachment; filename="kokoro-speech.mp3"',
                             "Cache-Control": "no-store"})
