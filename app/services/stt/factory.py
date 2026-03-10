"""STT provider factory: returns the provider selected in settings."""

import logging
from typing import Optional

from app.core.config import settings
from app.services.stt.base import STTProvider
from app.services.stt.deepgram import DeepgramSTTProvider

logger = logging.getLogger(__name__)


def get_stt_provider() -> Optional[STTProvider]:
    """Return the STT provider for server-side transcription, or None if client-only (webkit)."""
    name = (settings.stt_provider or "deepgram").strip().lower()
    if name == "deepgram":
        if not settings.deepgram_api_key or settings.deepgram_api_key.startswith("your_"):
            logger.warning("STT_PROVIDER=deepgram but DEEPGRAM_API_KEY not set; server STT unavailable")
            return None
        return DeepgramSTTProvider()
    if name == "webkit":
        return None
    logger.warning("Unknown STT_PROVIDER=%r, defaulting to deepgram if key set", settings.stt_provider)
    if settings.deepgram_api_key and not settings.deepgram_api_key.startswith("your_"):
        return DeepgramSTTProvider()
    return None
