"""TTS provider: Deepgram (REST + WebSocket Speak for voice agent)."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from urllib.parse import urlencode

from deepgram import AsyncDeepgramClient
from deepgram.speak.v1.types import SpeakV1Flush, SpeakV1Text

from app.core.config import settings
from app.services.tts.base import TTSStreamError

logger = logging.getLogger(__name__)

# REST: default encoding for stream_tts (matches common browser playback)
DEEPGRAM_REST_ENCODING = "mp3"
# WebSocket: linear16 is low-latency; client may need to match sample_rate
DEEPGRAM_WS_ENCODING = "linear16"
DEEPGRAM_WS_SAMPLE_RATE = "24000"
# Longer open timeout for Deepgram Speak WebSocket (default is 10s).
DEEPGRAM_SPEAK_WS_OPEN_TIMEOUT = 30.0


class DeepgramSpeakSession:
    """Persistent Deepgram TTS Speak WebSocket session for the voice agent."""

    def __init__(self, socket_client) -> None:
        self._conn = socket_client
        self._closed = False

    async def send_text_chunk(self, text: str) -> None:
        if not text.strip():
            return
        logger.debug("[tts] send_text len=%d", len(text))
        await self._conn.send_text(SpeakV1Text(type="Speak", text=text))

    async def send_flush(self) -> None:
        logger.debug("[tts] send_flush")
        await self._conn.send_flush(SpeakV1Flush(type="Flush"))

    async def receive_audio_chunks(self) -> AsyncIterator[bytes]:
        """Yield raw audio bytes as they arrive from Deepgram. Stops when we get Flushed (end of response)."""
        n_chunks, n_bytes = 0, 0
        try:
            while not self._closed:
                msg = await self._conn.recv()
                if isinstance(msg, bytes):
                    n_chunks += 1
                    n_bytes += len(msg)
                    yield msg
                else:
                    # Flushed = Deepgram finished sending audio for this turn; stop so pipeline can complete.
                    if getattr(msg, "type", None) == "Flushed":
                        logger.debug("[tts] received Flushed, ending audio stream")
                        return
        except Exception as e:
            if not self._closed:
                logger.debug("[tts] receive_audio_chunks ended after chunks=%d bytes=%d: %s", n_chunks, n_bytes, e)
            raise
        finally:
            logger.debug("[tts] receive_audio_chunks total chunks=%d bytes=%d", n_chunks, n_bytes)

    async def close(self) -> None:
        logger.debug("[tts] session close")
        self._closed = True
        if hasattr(self._conn, "_websocket") and self._conn._websocket:
            await self._conn._websocket.close()


class DeepgramProvider:
    """Deepgram TTS: REST for POST /voice/speak, WebSocket session for voice agent."""

    def __init__(self) -> None:
        self._api_key = settings.deepgram_api_key
        self._model = settings.deepgram_tts_model or "aura-asteria-en"

    def _client(self) -> AsyncDeepgramClient:
        return AsyncDeepgramClient(api_key=self._api_key)

    @property
    def media_type(self) -> str:
        return "audio/mpeg"

    async def check_available(self) -> None:
        if not self._api_key or self._api_key.startswith("your_"):
            raise TTSStreamError(
                "Deepgram TTS is not configured. Set DEEPGRAM_API_KEY in .env."
            )
        # Light check: create client and open/close speak connection would be heavy;
        # key presence is enough for now.

    async def stream_tts(
        self,
        text: str,
        *,
        streaming_quality: str = "balanced",
        streaming_strategy: str = "sentence",
        streaming_chunk_size: int = 200,
    ) -> AsyncIterator[bytes]:
        """Stream TTS via Deepgram REST (POST /v1/speak)."""
        client = self._client()
        try:
            async for chunk in client.speak.v1.audio.generate(
                text=text,
                model=self._model,
                encoding=DEEPGRAM_REST_ENCODING,
            ):
                if chunk:
                    yield chunk
        except Exception as e:
            logger.exception("Deepgram TTS REST failed: %s", e)
            raise TTSStreamError(str(e)) from e

    @asynccontextmanager
    async def open_tts_speak_session(
        self,
        *,
        model: Optional[str] = None,
        encoding: Optional[str] = None,
        sample_rate: Optional[str] = None,
    ):
        """
        Open a persistent Deepgram Speak WebSocket for the voice agent.
        Yield a session that accepts text chunks and streams audio back.
        """
        await self.check_available()
        client = self._client()
        model = model or self._model
        encoding = encoding or DEEPGRAM_WS_ENCODING
        sample_rate = sample_rate or DEEPGRAM_WS_SAMPLE_RATE
        logger.info("[tts] opening Deepgram Speak session (model=%s encoding=%s sample_rate=%s)...", model, encoding, sample_rate)
        session: Optional[DeepgramSpeakSession] = None
        try:
            async with client.speak.v1.connect(
                model=model,
                encoding=encoding,
                sample_rate=sample_rate,
            ) as dg_conn:
                logger.info("[tts] Deepgram Speak session connected")
                session = DeepgramSpeakSession(dg_conn)
                yield session
        except Exception as e:
            logger.exception("[tts] Deepgram Speak session error: %s", e)
            raise
        finally:
            if session:
                await session.close()
                logger.debug("[tts] Deepgram Speak session closed")
