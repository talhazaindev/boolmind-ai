"""WebSocket voice agent: real-time audio/text → STT → LLM → TTS → client."""

import asyncio
import base64
import json
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.stt import get_stt_provider
from app.services.tts.factory import get_tts_provider
from app.services.voice_logging import VoiceTurnTimings, log_audio_chunk, log_audio_summary
from app.services.voice_pipeline import run_voice_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


def _conn_id(ws: WebSocket) -> str:
    """Short id for logging (avoid logging full object)."""
    return hex(id(ws))[-6:]


async def _send_json(ws: WebSocket, obj: dict[str, Any]) -> None:
    try:
        await ws.send_json(obj)
    except Exception as e:
        logger.warning("voice_ws send_json failed: %s", e, exc_info=True)
        raise


async def _send_bytes(ws: WebSocket, data: bytes) -> None:
    try:
        await ws.send_bytes(data)
    except Exception as e:
        logger.warning("voice_ws send_bytes failed (len=%d): %s", len(data), e, exc_info=True)
        raise


@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket) -> None:
    """Real-time voice agent: config (session_id) first, then text or audio; receive transcript, llm_chunk, audio."""
    cid = _conn_id(websocket)
    await websocket.accept()
    logger.info("[voice_ws][%s] connection accepted", cid)
    await _send_json(websocket, {"type": "ready"})

    session_id: Optional[str] = None
    stt_provider = get_stt_provider()
    tts_provider = get_tts_provider()
    use_deepgram_stt = stt_provider is not None
    use_deepgram_tts = getattr(tts_provider, "open_tts_speak_session", None) is not None
    logger.info(
        "[voice_ws][%s] providers: stt=%s (use_deepgram=%s), tts=%s (use_deepgram_ws=%s)",
        cid,
        type(stt_provider).__name__ if stt_provider else "none",
        use_deepgram_stt,
        type(tts_provider).__name__,
        use_deepgram_tts,
    )

    stt_audio_queue: Optional[asyncio.Queue[Optional[bytes]]] = None
    stt_task: Optional[asyncio.Task] = None
    tts_session_context = None
    tts_session = None
    pipeline_lock = asyncio.Lock()
    audio_received = {"frames": 0, "bytes": 0}
    t_audio_session_start: Optional[float] = None  # set on config, used for per-chunk elapsed

    def _on_llm_chunk(text: str) -> None:
        asyncio.create_task(_send_json(websocket, {"type": "llm_chunk", "text": text}))

    def _on_audio_chunk(chunk: bytes) -> None:
        asyncio.create_task(_send_bytes(websocket, chunk))

    async def _run_pipeline(user_message: str) -> None:
        logger.info("[voice_ws][%s] pipeline start session_id=%s message_len=%d", cid, session_id, len(user_message))
        t0 = time.monotonic()
        timings = VoiceTurnTimings(conn_id=cid)
        async with pipeline_lock:
            if use_deepgram_tts and tts_session is not None:
                await run_voice_pipeline(
                    session_id,
                    user_message,
                    on_llm_chunk=_on_llm_chunk,
                    on_audio_chunk=_on_audio_chunk,
                    tts_speak_session=tts_session,
                    conn_id=cid,
                    voice_timings=timings,
                )
            else:
                await run_voice_pipeline(
                    session_id,
                    user_message,
                    on_llm_chunk=_on_llm_chunk,
                    on_audio_chunk=_on_audio_chunk,
                    tts_speak_session=None,
                    conn_id=cid,
                    voice_timings=timings,
                )
        logger.info("[voice_ws][%s] pipeline done in %.2fs", cid, time.monotonic() - t0)

    async def _stt_consumer(audio_queue: asyncio.Queue[Optional[bytes]]) -> None:
        """Consume STT events and run pipeline on final transcript."""
        if stt_provider is None:
            return
        logger.info("[voice_ws][%s] STT consumer starting", cid)
        async def audio_iter():
            n_chunks = 0
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    logger.debug("[voice_ws][%s] STT audio stream end (chunks=%d)", cid, n_chunks)
                    return
                n_chunks += 1
                yield chunk

        try:
            async for event in stt_provider.stream_transcribe(audio_iter()):
                await _send_json(
                    websocket,
                    {"type": "transcript", "text": event.text, "is_final": event.is_final},
                )
                logger.debug("[voice_ws][%s] transcript is_final=%s text=%r", cid, event.is_final, (event.text[:80] + "…" if len(event.text) > 80 else event.text))
                if event.is_final and event.text.strip() and session_id:
                    await _run_pipeline(event.text.strip())
        except asyncio.CancelledError:
            logger.info("[voice_ws][%s] STT consumer cancelled", cid)
        except Exception as e:
            logger.exception("[voice_ws][%s] STT consumer error: %s", cid, e)
            await _send_json(websocket, {"type": "error", "message": str(e)})

    try:
        while True:
            raw = await websocket.receive()
            text = raw.get("text")
            bytes_data = raw.get("bytes")
            if bytes_data is not None:
                audio_received["frames"] += 1
                audio_received["bytes"] += len(bytes_data)
                elapsed = (time.monotonic() - t_audio_session_start) if t_audio_session_start else 0.0
                n = audio_received["frames"]
                log_audio_chunk(cid, n, len(bytes_data), elapsed, emit_rich=(n <= 3 or n % 10 == 1))
                if n == 1:
                    logger.info("[voice_ws][%s] first audio frame received len=%d", cid, len(bytes_data))
                elif n % 50 == 0:
                    logger.info("[voice_ws][%s] audio frames=%d total_bytes=%d", cid, audio_received["frames"], audio_received["bytes"])
            if text:
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    await _send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                    continue
                msg_type = msg.get("type")
                logger.debug("[voice_ws][%s] recv type=%s", cid, msg_type)
                if msg_type == "config":
                    sid = msg.get("session_id")
                    if not sid:
                        logger.warning("[voice_ws][%s] config missing session_id", cid)
                        await _send_json(websocket, {"type": "error", "message": "config requires session_id"})
                        continue
                    session_id = str(sid)
                    audio_received["frames"] = 0
                    audio_received["bytes"] = 0
                    t_audio_session_start = time.monotonic()
                    logger.info("[voice_ws][%s] config session_id=%s", cid, session_id)
                    if stt_task and not stt_task.done():
                        logger.debug("[voice_ws][%s] cancelling previous STT task", cid)
                        stt_task.cancel()
                        try:
                            await stt_task
                        except asyncio.CancelledError:
                            pass
                    old_queue = stt_audio_queue
                    stt_audio_queue = asyncio.Queue() if use_deepgram_stt else None
                    if old_queue is not None:
                        try:
                            old_queue.put_nowait(None)
                        except asyncio.QueueFull:
                            pass
                    prev_ctx = tts_session_context
                    prev_session = tts_session
                    tts_session_context = None
                    tts_session = None
                    if prev_session is not None:
                        try:
                            await prev_session.close()
                        except Exception as ex:
                            logger.debug("[voice_ws][%s] prev TTS close: %s", cid, ex)
                    if prev_ctx is not None:
                        try:
                            await prev_ctx.__aexit__(None, None, None)
                        except Exception as ex:
                            logger.debug("[voice_ws][%s] prev TTS context exit: %s", cid, ex)
                    if use_deepgram_tts and tts_provider and session_id:
                        logger.info("[voice_ws][%s] opening Deepgram TTS Speak session...", cid)
                        t0_tts = time.monotonic()
                        try:
                            tts_session_context = tts_provider.open_tts_speak_session()
                            tts_session = await tts_session_context.__aenter__()
                            logger.info("[voice_ws][%s] Deepgram TTS Speak session open in %.2fs", cid, time.monotonic() - t0_tts)
                        except Exception as ex:
                            logger.exception("[voice_ws][%s] Deepgram TTS Speak session failed after %.2fs: %s", cid, time.monotonic() - t0_tts, ex)
                            await _send_json(websocket, {"type": "error", "message": str(ex)})
                            continue
                    if use_deepgram_stt and stt_audio_queue is not None:
                        logger.info("[voice_ws][%s] starting STT consumer task", cid)
                        stt_task = asyncio.create_task(_stt_consumer(stt_audio_queue))
                    await _send_json(websocket, {"type": "ready"})
                    logger.info("[voice_ws][%s] ready sent", cid)
                elif msg_type == "text":
                    if not session_id:
                        await _send_json(websocket, {"type": "error", "message": "Send config with session_id first"})
                        continue
                    user_text = (msg.get("text") or "").strip()
                    if user_text:
                        await _run_pipeline(user_text)
                elif msg_type == "end_utterance":
                    elapsed = (time.monotonic() - t_audio_session_start) if t_audio_session_start else 0.0
                    log_audio_summary(cid, audio_received["frames"], audio_received["bytes"], elapsed)
                    logger.info(
                        "[voice_ws][%s] end_utterance (this session: frames=%d bytes=%d)",
                        cid, audio_received["frames"], audio_received["bytes"],
                    )
                    if audio_received["frames"] == 0:
                        logger.warning(
                            "[voice_ws][%s] end_utterance but no binary audio received — check client sends mic as WebSocket binary frames",
                            cid,
                        )
                    if stt_audio_queue is not None:
                        try:
                            stt_audio_queue.put_nowait(None)
                        except asyncio.QueueFull:
                            pass
                elif msg_type == "audio":
                    b64 = msg.get("data")
                    if b64 and stt_audio_queue is not None:
                        try:
                            stt_audio_queue.put_nowait(base64.b64decode(b64))
                        except (ValueError, asyncio.QueueFull):
                            pass
            if bytes_data is not None:
                if stt_audio_queue is not None:
                    try:
                        stt_audio_queue.put_nowait(bytes_data)
                    except asyncio.QueueFull:
                        logger.warning("[voice_ws][%s] STT audio queue full, dropping %d bytes", cid, len(bytes_data))
                else:
                    logger.debug("[voice_ws][%s] binary received but no STT queue (stt not active?)", cid)
    except WebSocketDisconnect:
        logger.info("[voice_ws][%s] client disconnected", cid)
    except Exception as e:
        logger.exception("[voice_ws][%s] error: %s", cid, e)
        try:
            await _send_json(websocket, {"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        logger.info("[voice_ws][%s] cleanup", cid)
        if stt_task and not stt_task.done():
            stt_task.cancel()
            try:
                await stt_task
            except asyncio.CancelledError:
                pass
        if tts_session_context is not None and tts_session is not None:
            try:
                await tts_session.close()
                await tts_session_context.__aexit__(None, None, None)
                logger.debug("[voice_ws][%s] TTS session closed", cid)
            except Exception as e:
                logger.warning("[voice_ws][%s] TTS session close: %s", cid, e)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("[voice_ws][%s] connection closed", cid)
