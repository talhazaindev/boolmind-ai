# AI Backend

FastAPI + Groq LLM service with knowledge base and session memory.

## Setup with uv

This project uses **Python 3.11**.

```bash
# Install uv (if needed): https://docs.astral.sh/uv/

# Use Python 3.11 (install if missing, then pin)
uv python install 3.11
uv python pin 3.11

uv sync
```

## Run

```bash
# Development (reload on change)
uv run uvicorn main:app --reload

# Production
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## Environment

Copy `.env.example` to `.env` and set `GROQ_API_KEY`.

## Frontend

With the server running, open **http://127.0.0.1:8000/** in a browser to use the chat UI. It streams responses token-by-token and keeps conversation history per session.

## Voice (TTS + STT)

- **TTS**: Choose a provider via **`TTS_PROVIDER`** in `.env`:
  - **`chatterbox`** (default) — self-hosted [Chatterbox TTS API](https://github.com/travisvn/chatterbox-tts-api), streams WAV from `CHATTERBOX_TTS_URL`.
  - **`elevenlabs`** — [ElevenLabs](https://elevenlabs.io) cloud API, streams MP3. Set `ELEVENLABS_API_KEY` (and optionally `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`).
- **STT**: Done in the browser via the [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) (webkit). **Record** uses the browser’s speech recognition; **Speak** streams TTS from the configured provider.

### How to start Chatterbox (TTS) when `TTS_PROVIDER=chatterbox`

This app expects TTS at **http://localhost:4123**. To get that, run Chatterbox in a **second terminal** (keep your ai-backend running in the first). There is no pre-built Docker image — clone the repo and run one of the options below.

**Terminal 1 (this app):** `uv run uvicorn main:app --reload`  
**Terminal 2 (Chatterbox):** run one of the following so it listens on port 4123.

**Docker:**

```bash
git clone https://github.com/travisvn/chatterbox-tts-api
cd chatterbox-tts-api
cp .env.example.docker .env
docker compose -f docker/docker-compose.yml up -d
```

CPU-only: use `docker/docker-compose.cpu.yml`. First run may be slow (build + model download).

**Local (uv, no Docker):**

```bash
git clone https://github.com/travisvn/chatterbox-tts-api
cd chatterbox-tts-api
uv sync && cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 4123
```

Once Chatterbox is up, (re)load the chat UI — **Speak** will use `http://localhost:4123` automatically.

## API

- `POST /chat/stream` — streaming chat (body: `message`, `session_id`)
- `GET /sessions/{session_id}` — conversation history
- `POST /sessions/new` — create session (optional query: `?session_id=...`)
- `POST /voice/speak` — TTS: body `{ "text": "..." }`, returns streaming audio (WAV or MP3 depending on provider)
- `GET /voice/ws` — WebSocket voice agent (see Voice agent above)
- `POST /voice/transcribe` — when `STT_PROVIDER=deepgram`: multipart file upload, returns `{ "text": "..." }`
- `GET /health` — health check
