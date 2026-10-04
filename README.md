# Kokoro Local

A localhost browser app for generating speech with Kokoro. Choose an American or British English voice, adjust speech speed, enter text with optional pause tags, generate, play, and download an MP3. Inference runs on your computer; model and voice files are downloaded on first use.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. uv will provision Python 3.12 if needed. The Python dependencies include an espeak-ng loader for English phonemization.

```bash
uv venv --python 3.12
uv pip install -r requirements.txt
uv run --no-project -- uvicorn app:app --host 127.0.0.1 --port 8000
```

On Windows, use the same commands in PowerShell. If phonemization reports a missing espeak-ng library, install espeak-ng and make it discoverable by Kokoro.

Open **http://127.0.0.1:8000**. The first generation needs an internet connection to fetch Kokoro's model and selected voice from Hugging Face, and may also install the English spaCy model. Subsequent generations use cached files. No hosted inference API is used. Audio generation may be slow on CPU; GPU acceleration depends on your PyTorch installation.

Set speed between 0.5× and 2× (1× is normal). For explicit silence, include a tag such as `Hello. <break time="0.2s" /> Next sentence.` Pauses support seconds, up to 10 seconds per tag, 50 tags, and 60 seconds total. Pause tags split the text into separately synthesized segments; normal punctuation may add its own natural pause as well. Malformed break tags are rejected instead of spoken aloud.

To stop the server, press Ctrl+C in the terminal. Inputs are limited to 5,000 characters per generation. Generated audio is returned directly to your browser and is not saved by the server.
