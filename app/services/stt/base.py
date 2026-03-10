"""STT provider protocol: stream of audio chunks -> stream of transcript events."""

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


class STTStreamError(Exception):
    """STT request or stream failed."""

    pass


@dataclass
class TranscriptEvent:
    """A single transcript result from the STT provider."""

    text: str
    is_final: bool


class STTProvider(Protocol):
    """Protocol for STT providers. Stream audio in, stream transcript events out."""

    async def stream_transcribe(
        self,
        audio_chunks: AsyncIterator[bytes],
    ) -> AsyncIterator[TranscriptEvent]:
        """Consume audio chunks and yield transcript events (interim and final)."""
        ...

    async def check_available(self) -> None:
        """Raise STTStreamError if the provider is not configured or reachable."""
        ...
