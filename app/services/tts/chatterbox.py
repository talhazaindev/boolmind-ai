"""TTS provider: Chatterbox (local/self-hosted) streaming API."""

import logging
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.services.tts.base import TTSStreamError

logger = logging.getLogger(__name__)


class ChatterboxProvider:
    """Stream WAV from Chatterbox TTS API (localhost or custom URL)."""

    def __init__(self) -> None:
        self._base = settings.chatterbox_tts_url.rstrip("/")

    @property
    def media_type(self) -> str:
        return "audio/wav"

    async def check_available(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.get(self._base)
        except httpx.RequestError as e:
            raise TTSStreamError(
                f"TTS service is not running at {self._base}. "
                "Start Chatterbox TTS (see README) or set CHATTERBOX_TTS_URL in .env."
            ) from e

    async def stream_tts(
        self,
        text: str,
        *,
        streaming_quality: str = "balanced",
        streaming_strategy: str = "sentence",
        streaming_chunk_size: int = 200,
    ) -> AsyncIterator[bytes]:
        url = f"{self._base}/v1/audio/speech/stream"
        payload = {
            "input": text,
            "streaming_quality": streaming_quality,
            "streaming_strategy": streaming_strategy,
            "streaming_chunk_size": streaming_chunk_size,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise TTSStreamError(
                            f"TTS API returned {response.status_code}: {body.decode(errors='replace')[:500]}"
                        )
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            yield chunk
        except httpx.RequestError as e:
            logger.exception("Chatterbox TTS request failed: %s", e)
            raise TTSStreamError(str(e)) from e
