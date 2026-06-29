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

# FIDP / local diffusion (optional):
uv sync --extra fidp
```

## Run

```bash
# Development (reload on change)
uv run uvicorn main:app --reload

# Production
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker

### Local stack (recommended for dev)

Separate infrastructure services plus the API:

| Service | Image | Port | Role |
|---------|-------|------|------|
| **redis** | `redis:7-alpine` | 6379 | Session history (`REDIS_BACKEND=local`) |
| **pinecone** | `pinecone-index` (384-dim cosine) | 5081 | Vector RAG (`PINECONE_MODE=local`) |
| **advisor-api** | `Dockerfile` | 8000 | FastAPI + static UI |

Groq, HubSpot, Cal.com, Resend, etc. remain **cloud APIs** configured in `.env`.

```bash
cp .env.docker.example .env   # add GROQ_API_KEY
docker compose up -d --build
# Seed knowledge base (once):
docker compose --profile seed run --rm ingest --namespace retify
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000/advisor | Advisor chat UI |
| http://localhost:8000/health | Health + integration readiness |
| http://localhost:8000/admin | Admin stats |

**Cloud-only** (Upstash + hosted Pinecone, API container only):

```bash
cp .env.example .env   # UPSTASH_*, PINECONE_*, GROQ_*
docker compose -f docker-compose.cloud.yml up -d --build
```

**Profiles:** `gpu` (CUDA FIDP), `voice` (Chatterbox TTS), `seed` (RAG ingest job).

Files: `docker-compose.yml`, `docker-compose.cloud.yml`, `.env.docker.example`, `Dockerfile`, `Dockerfile.gpu`.

## Environment

Copy `.env.example` to `.env` and set `GROQ_API_KEY`.

## Boolmind Advisor (Phase 1)

Product-aware advisor with Groq tool calling, Pinecone RAG, and Redis sessions (Upstash or local).

### Setup

1. Copy `.env.example` to `.env` and fill **Tier A** keys (`GROQ_*`, `PINECONE_*`, `UPSTASH_*`).
2. Embeddings use **local BGE** by default (`EMBEDDING_PROVIDER=local`) — no OpenAI key required.
3. Create a **384-dimension** Pinecone index (see below), then ingest:

```bash
python scripts/create_pinecone_index.py
python scripts/run_ingest.py --namespace retify
```

### Pinecone + BGE setup

Your old `boolmind-knowledge` index is **1536 dims** (OpenAI). BGE small needs a **new** index:

| Setting | Value |
|---------|--------|
| Name | `boolmind-knowledge-bge` |
| Dimensions | **384** |
| Metric | **cosine** |
| Type | Serverless |

**Console:** [app.pinecone.io](https://app.pinecone.io) → Create Index → dimension `384`, metric `cosine`.

**CLI script:** `python scripts/create_pinecone_index.py` (prints `PINECONE_HOST` for `.env`).

Then set in `.env`:

```env
EMBEDDING_PROVIDER=local
EMBEDDING_DIMENSION=384
PINECONE_INDEX_NAME=boolmind-knowledge-bge
PINECONE_HOST=https://<your-new-index-host>.pinecone.io
```

3. Start the server:

```bash
uv run uvicorn main:app --reload
# or: python -m uvicorn main:app --reload
```

4. Open **http://127.0.0.1:8000/advisor** (or `frontend/advisor.html` via the `/advisor` route).

### API

- `POST /api/chat-init` — create session, opening message
- `POST /api/chat` — SSE stream (`delta`, `tool_start`, `tool_result`, `done`, `error`)
- `GET /health` — includes `advisor_tier_a_ready`

### Local GPU (FIDP / diffusion models)

For **RTX 3050 6GB** (or similar), use CUDA PyTorch and store Hugging Face weights on **D:** (keeps **C:** free).

1. From repo root in PowerShell:

```powershell
.\scripts\setup_gpu.ps1
```

2. Add to `.env` (created by the script if missing):

```env
HF_HOME=D:\boolmind-ai\ml-cache
FIDP_OUTPUT_DIR=D:\boolmind-ai\fidp-output
```

3. Verify:

```powershell
.\.venv\Scripts\python.exe scripts\verify_gpu.py
```

Expect `cuda available: True` and your GPU name. **Embeddings stay on CPU** by default so 6 GB VRAM is left for FIDP.

### Local FIDP (SDXL Turbo)

In `.env`:

```env
IMAGE_GEN_PROVIDER=local
IMAGE_GEN_MODEL=stabilityai/sdxl-turbo
IMAGE_GEN_STEPS=2
IMAGE_GEN_SIZE=512
HF_HOME=D:\boolmind-ai\ml-cache
FIDP_OUTPUT_DIR=D:\boolmind-ai\fidp-output
```

First `generate_fidp` call downloads the model to `HF_HOME` on D: (several GB). Generated previews are served at `/fidp/<file>.png`. Use `IMAGE_GEN_PROVIDER=mock` to skip GPU.

With **uv** instead of pip-only:

```bash
uv sync --extra fidp --extra gpu
```

### Tests

```bash
python -m pytest tests/unit -q
```

## Frontend (legacy)

With the server running, open **http://127.0.0.1:8000/** in a browser to use the legacy Groq chat UI.

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
