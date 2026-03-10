"""STT providers: factory and protocol. Use get_stt_provider() for server-side STT (e.g. voice agent)."""

from app.services.stt.base import STTStreamError, STTProvider, TranscriptEvent
from app.services.stt.factory import get_stt_provider

__all__ = ["STTStreamError", "STTProvider", "TranscriptEvent", "get_stt_provider"]
