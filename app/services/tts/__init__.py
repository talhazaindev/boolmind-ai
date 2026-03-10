"""TTS providers: factory and provider interface. Use get_tts_provider() and then check_available() / stream_tts()."""

from app.services.tts.base import TTSStreamError, TTSProvider
from app.services.tts.factory import get_tts_provider

__all__ = ["TTSStreamError", "TTSProvider", "get_tts_provider"]
