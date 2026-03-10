"""TTS provider protocol: all providers implement this interface."""

from typing import AsyncIterator, Protocol


class TTSStreamError(Exception):
    """TTS request or stream failed."""

    pass


class TTSProvider(Protocol):
    """Protocol for TTS providers. Implement check_available() and stream_tts()."""

    @property
    def media_type(self) -> str:
        """Response media type, e.g. 'audio/wav' or 'audio/mpeg'."""
        ...

    async def check_available(self) -> None:
        """Raise TTSStreamError if the provider is not reachable or not configured."""
        ...

    async def stream_tts(
        self,
        text: str,
        *,
        streaming_quality: str = "balanced",
        streaming_strategy: str = "sentence",
        streaming_chunk_size: int = 200,
    ) -> AsyncIterator[bytes]:
        """Stream raw audio bytes. Provider may ignore unused kwargs."""
        ...
