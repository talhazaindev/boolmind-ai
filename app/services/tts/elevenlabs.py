"""TTS provider: ElevenLabs cloud API (streaming)."""

import logging
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.services.tts.base import TTSStreamError

logger = logging.getLogger(__name__)

ELEVENLABS_STREAM_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"


class ElevenLabsProvider:
    """Stream MP3 from ElevenLabs text-to-speech API."""

    def __init__(self) -> None:
        self._api_key = settings.elevenlabs_api_key
        self._voice_id = settings.elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel default
        self._model_id = settings.elevenlabs_model_id or "eleven_multilingual_v2"

    @property
    def media_type(self) -> str:
        return "audio/mpeg"

    async def check_available(self) -> None:
        if not self._api_key or self._api_key.startswith("your_"):
            raise TTSStreamError(
                "ElevenLabs is not configured. Set ELEVENLABS_API_KEY in .env (get a key at elevenlabs.io)."
            )
        # Optional: light check (e.g. GET /v1/user) to verify key; for now we only require key set
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers={"xi-api-key": self._api_key, "Content-Type": "application/json"},
                )
                if r.status_code == 401:
                    raise TTSStreamError("ElevenLabs API key is invalid. Check ELEVENLABS_API_KEY in .env.")
        except httpx.RequestError as e:
            raise TTSStreamError(f"Could not reach ElevenLabs API: {e}") from e

    async def stream_tts(
        self,
        text: str,
        *,
        streaming_quality: str = "balanced",
        streaming_strategy: str = "sentence",
        streaming_chunk_size: int = 200,
    ) -> AsyncIterator[bytes]:
        url = ELEVENLABS_STREAM_URL.format(voice_id=self._voice_id)
        payload = {"text": text, "model_id": self._model_id}
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise TTSStreamError(
                            f"ElevenLabs API returned {response.status_code}: {body.decode(errors='replace')[:500]}"
                        )
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            yield chunk
        except httpx.RequestError as e:
            logger.exception("ElevenLabs TTS request failed: %s", e)
            raise TTSStreamError(str(e)) from e
