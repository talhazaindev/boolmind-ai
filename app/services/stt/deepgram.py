"""STT provider: Deepgram Live WebSocket streaming transcription."""

import asyncio
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

from app.core.config import settings
from app.services.stt.base import STTStreamError, TranscriptEvent

logger = logging.getLogger(__name__)

# Longer open timeout for Deepgram WebSocket (default websockets is 10s; slow networks need more).
DEEPGRAM_WS_OPEN_TIMEOUT = 30.0


class DeepgramSTTProvider:
    """Stream transcription via Deepgram Live (wss://api.deepgram.com/v1/listen)."""

    def __init__(self) -> None:
        self._api_key = settings.deepgram_api_key
        self._model = settings.deepgram_stt_model or "nova-2"

    async def check_available(self) -> None:
        if not self._api_key or self._api_key.startswith("your_"):
            raise STTStreamError(
                "Deepgram is not configured. Set DEEPGRAM_API_KEY in .env (get a key at deepgram.com)."
            )

    async def stream_transcribe(
        self,
        audio_chunks: AsyncIterator[bytes],
    ) -> AsyncIterator[TranscriptEvent]:
        """Forward audio to Deepgram Live; yield transcript events from the connection."""
        try:
            from websockets.legacy.client import connect as ws_connect
            from deepgram.listen.v1.socket_client import AsyncV1SocketClient
        except ImportError as e:
            raise STTStreamError("deepgram-sdk and websockets are required. pip install deepgram-sdk websockets") from e

        query = urlencode({
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": "16000",
            "interim_results": "true",
            "punctuate": "true",
            "language": "en",
        })
        ws_url = f"wss://api.deepgram.com/v1/listen?{query}"
        headers = {"Authorization": f"Token {self._api_key}"}
        logger.info("[stt] connecting to Deepgram Listen (model=%s, encoding=linear16, 16kHz)...", self._model)

        queue: asyncio.Queue[TranscriptEvent | None] = asyncio.Queue()

        async def recv_loop(conn: AsyncV1SocketClient) -> None:
            try:
                while True:
                    msg = await conn.recv()
                    type_name = type(msg).__name__
                    if type_name == "ListenV1ResultsEvent":
                        channel = getattr(msg, "channel", None)
                        if channel:
                            alts = getattr(channel, "alternatives", [])
                            if alts:
                                transcript = (getattr(alts[0], "transcript", None) or "").strip()
                                if transcript:
                                    is_final = getattr(msg, "is_final", True)
                                    logger.debug("[stt] transcript is_final=%s len=%d", is_final, len(transcript))
                                    queue.put_nowait(TranscriptEvent(text=transcript, is_final=is_final))
            except asyncio.CancelledError:
                logger.debug("[stt] recv_loop cancelled")
            except Exception as e:
                if "ConnectionClosedOK" in type(e).__name__ or "1000" in str(e):
                    logger.debug("[stt] recv_loop connection closed (expected after end_utterance)")
                else:
                    logger.warning("[stt] recv_loop: %s", e, exc_info=True)
            finally:
                queue.put_nowait(None)

        async def feed_audio(conn: AsyncV1SocketClient) -> None:
            n_chunks, n_bytes = 0, 0
            try:
                async for chunk in audio_chunks:
                    if chunk:
                        await conn._send(chunk)
                        n_chunks += 1
                        n_bytes += len(chunk)
                logger.debug("[stt] feed_audio done chunks=%d bytes=%d", n_chunks, n_bytes)
            except asyncio.CancelledError:
                logger.debug("[stt] feed_audio cancelled after chunks=%d bytes=%d", n_chunks, n_bytes)
            except Exception as e:
                logger.exception("[stt] feed_audio error after chunks=%d bytes=%d: %s", n_chunks, n_bytes, e)
            finally:
                try:
                    await conn._websocket.close()
                except Exception as ex:
                    logger.debug("[stt] websocket close: %s", ex)

        try:
            async with ws_connect(
                ws_url,
                extra_headers=headers,
                open_timeout=DEEPGRAM_WS_OPEN_TIMEOUT,
            ) as raw_ws:
                logger.info("[stt] Deepgram Listen connected")
                conn = AsyncV1SocketClient(websocket=raw_ws)
                recv_task = asyncio.create_task(recv_loop(conn))
                feed_task = asyncio.create_task(feed_audio(conn))
                try:
                    while True:
                        event = await queue.get()
                        if event is None:
                            break
                        yield event
                finally:
                    feed_task.cancel()
                    recv_task.cancel()
                    try:
                        await feed_task
                    except asyncio.CancelledError:
                        pass
                    try:
                        await recv_task
                    except asyncio.CancelledError:
                        pass
        except asyncio.TimeoutError as e:
            logger.error("[stt] Deepgram Listen connection timed out after %.0fs", DEEPGRAM_WS_OPEN_TIMEOUT)
            raise STTStreamError(
                f"Connection to Deepgram timed out. Check network or try again (timeout={DEEPGRAM_WS_OPEN_TIMEOUT}s)."
            ) from e
        except Exception as e:
            logger.exception("[stt] Deepgram STT error: %s", e)
            raise STTStreamError(str(e)) from e
