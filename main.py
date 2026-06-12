"""FastAPI + Groq LLM Service with Knowledge Base."""

import logging
import sys
from pathlib import Path

from app.core.ml_env import configure_ml_environment

configure_ml_environment()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import advisor, chat, sessions, voice, voice_ws
from app.advisor.mcp.mount import mount_advisor_mcp_servers
from app.core.config import settings

if settings.sentry_configured:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
    )

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

app.include_router(advisor.router, prefix="/api")
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(voice.router)
app.include_router(voice_ws.router)
mount_advisor_mcp_servers(app)


@app.get("/health")
async def health():
    """Health check; confirms LLM and advisor deps are configured (does not call API)."""
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider_resolved,
        "llm_configured": settings.llm_configured,
        "llm_model": settings.llm_model_resolved,
        "groq_configured": settings.groq_configured,
        "groq_key_pool_size": len(settings.get_groq_api_keys()),
        "advisor_tier_a_ready": settings.advisor_tier_a_ready,
        "image_gen_provider": settings.image_gen_provider,
        "local_image_gen_ready": settings.local_image_gen_ready,
    }


frontend_dir = Path(__file__).resolve().parent / "frontend"
fidp_output_dir = settings.fidp_output_path
fidp_output_dir.mkdir(parents=True, exist_ok=True)


@app.get("/admin")
async def admin_page():
    """Internal admin dashboard."""
    from fastapi.responses import FileResponse

    path = frontend_dir / "admin.html"
    if path.exists():
        return FileResponse(path)
    return {"error": "admin.html not found"}


@app.get("/advisor")
async def advisor_page():
    """Boolmind Advisor chat UI."""
    from fastapi.responses import FileResponse

    path = frontend_dir / "advisor.html"
    if path.exists():
        return FileResponse(path)
    return {"error": "advisor.html not found"}


# Generated FIDP images (local SDXL Turbo)
app.mount(
    "/fidp",
    StaticFiles(directory=str(fidp_output_dir)),
    name="fidp",
)

# Serve frontend last so API routes take precedence
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.on_event("startup")
async def startup():
    logger.info("Starting %s", settings.app_name)
    if settings.image_gen_provider.strip().lower() == "local":
        if settings.local_image_gen_ready:
            logger.info(
                "FIDP local SDXL Turbo enabled; output dir=%s (lazy load on first request)",
                fidp_output_dir,
            )
        else:
            logger.warning(
                "IMAGE_GEN_PROVIDER=local but CUDA unavailable — FIDP will fall back to placeholder"
            )
    if getattr(settings, "voice_rich_logs", False) or settings.debug:
        try:
            from app.services.voice_logging import setup_rich_voice_logging
            setup_rich_voice_logging()
            logger.info("Voice Rich logging enabled")
        except Exception as e:
            logger.debug("Voice Rich logging not available: %s", e)