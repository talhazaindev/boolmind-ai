"""FastAPI + Groq LLM Service with Knowledge Base."""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import chat, sessions, voice, voice_ws
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Chat API with Groq LLM, knowledge base, and session memory",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(voice.router)
app.include_router(voice_ws.router)


@app.get("/health")
async def health():
    """Health check; confirms Groq is configured (does not call API)."""
    return {
        "status": "ok",
        "groq_configured": settings.groq_configured,
    }


# Serve frontend last so API routes take precedence
frontend_dir = Path(__file__).resolve().parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.on_event("startup")
async def startup():
    logger.info("Starting %s", settings.app_name)
    if getattr(settings, "voice_rich_logs", False) or settings.debug:
        try:
            from app.services.voice_logging import setup_rich_voice_logging
            setup_rich_voice_logging()
            logger.info("Voice Rich logging enabled")
        except Exception as e:
            logger.debug("Voice Rich logging not available: %s", e)