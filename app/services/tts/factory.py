"""TTS provider factory: returns the provider selected in settings."""

import logging

from app.core.config import settings
from app.services.tts.base import TTSProvider, TTSStreamError
from app.services.tts.chatterbox import ChatterboxProvider
from app.services.tts.deepgram import DeepgramProvider
from app.services.tts.elevenlabs import ElevenLabsProvider

logger = logging.getLogger(__name__)


def get_tts_provider() -> TTSProvider:
    """Return the TTS provider configured in settings (e.g. TTS_PROVIDER=chatterbox|elevenlabs|deepgram)."""
    name = (settings.tts_provider or "chatterbox").strip().lower()
    if name == "elevenlabs":
        return ElevenLabsProvider()
    if name == "chatterbox":
        return ChatterboxProvider()
    if name == "deepgram":
        return DeepgramProvider()
    logger.warning("Unknown TTS_PROVIDER=%r, falling back to chatterbox", settings.tts_provider)
    return ChatterboxProvider()
