"""Voice pipeline: LLM stream → (optional) Deepgram TTS WebSocket or REST TTS; callbacks for chunks."""

import asyncio
import logging
import re
import time
from typing import Callable, Optional

from app.services.chat_service import ChatService
from app.services.tts.factory import get_tts_provider
from app.services.voice_logging import (
    VoiceTurnTimings,
    log_llm_chunk,
    log_llm_done,
    log_llm_input,
    log_tts_audio_chunk,
    log_tts_flushed,
    log_tts_sentence,
    log_turn_summary,
)

logger = logging.getLogger(__name__)

# Sentence boundary: . ! ? followed by space or end
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?])$")


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries; preserve trailing partial."""
    if not text.strip():
        return []
    parts = SENTENCE_END_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


async def run_voice_pipeline(
    session_id: str,
    user_message: str,
    *,
    on_llm_chunk: Callable[[str], None],
    on_audio_chunk: Callable[[bytes], None],
    tts_speak_session: Optional[object] = None,
    conn_id: Optional[str] = None,
    voice_timings: Optional[VoiceTurnTimings] = None,
) -> None:
    """
    Run LLM stream for session_id + user_message; stream TTS audio via callbacks.

    - If tts_speak_session is provided (Deepgram Speak WebSocket): push sentence-sized
      chunks to the session and relay audio from the session to on_audio_chunk.
    - Otherwise: buffer full LLM reply, then stream via get_tts_provider().stream_tts()
      and call on_audio_chunk for each chunk.
    """
    t_pipeline_start = time.monotonic()
    conn_id = conn_id or ""
    if voice_timings:
        voice_timings.t_start = t_pipeline_start
        voice_timings.add("Pipeline", f"start len={len(user_message)}")
    logger.info("[pipeline] start session_id=%r user_message_len=%d tts_ws=%s", session_id, len(user_message), tts_speak_session is not None)
    log_llm_input(conn_id, session_id, len(user_message), 0.0)
    chat = ChatService()
    buffer: list[str] = []

    async def consume_llm():
        nonlocal buffer
        try:
            async for chunk in chat.stream_reply(session_id, user_message):
                on_llm_chunk(chunk)
                buffer.append(chunk)
        except Exception as e:
            logger.exception("[pipeline] LLM error: %s", e)
            raise

    if tts_speak_session is not None:
        # Deepgram TTS WebSocket: on each LLM chunk, emit to client; on sentence boundary push to TTS; relay audio.
        send_text = getattr(tts_speak_session, "send_text_chunk", None)
        send_flush = getattr(tts_speak_session, "send_flush", None)
        receive_audio = getattr(tts_speak_session, "receive_audio_chunks", None)
        if not (send_text and receive_audio):
            raise ValueError("tts_speak_session must have send_text_chunk and receive_audio_chunks")

        last_sent_end = 0  # index into full text up to which we've sent sentences
        n_sentences = 0
        llm_chunk_count = 0
        t_llm_first = None

        async def consume_llm_and_push_sentences():
            nonlocal last_sent_end, n_sentences, llm_chunk_count, t_llm_first
            try:
                async for chunk in chat.stream_reply(session_id, user_message):
                    if t_llm_first is None:
                        t_llm_first = time.monotonic()
                        if voice_timings:
                            voice_timings.add("LLM", "first token")
                    on_llm_chunk(chunk)
                    buffer.append(chunk)
                    llm_chunk_count += 1
                    elapsed = time.monotonic() - t_pipeline_start
                    log_llm_chunk(
                        conn_id, llm_chunk_count, len(chunk), elapsed, chunk[:50],
                        emit_rich=(llm_chunk_count <= 3 or llm_chunk_count % 10 == 1),
                    )
                    full = "".join(buffer)
                    # Send only new complete sentences (avoid duplicates).
                    for m in SENTENCE_END_RE.finditer(full, last_sent_end):
                        end = m.end()
                        if end > last_sent_end:
                            sentence = full[last_sent_end:end].strip()
                            if sentence:
                                n_sentences += 1
                                t_sent = time.monotonic() - t_pipeline_start
                                if voice_timings:
                                    voice_timings.add("TTS in", f"sentence #{n_sentences} len={len(sentence)}")
                                log_tts_sentence(conn_id, n_sentences, len(sentence), t_sent, sentence)
                                logger.debug("[pipeline] sentence %d to TTS len=%d", n_sentences, len(sentence))
                                await send_text(sentence)
                            last_sent_end = end
                # Flush remainder
                remainder = full[last_sent_end:].strip() if buffer else ""
                if remainder:
                    n_sentences += 1
                    t_sent = time.monotonic() - t_pipeline_start
                    if voice_timings:
                        voice_timings.add("TTS in", f"remainder len={len(remainder)}")
                    log_tts_sentence(conn_id, n_sentences, len(remainder), t_sent, remainder)
                    logger.debug("[pipeline] remainder to TTS len=%d", len(remainder))
                    await send_text(remainder)
                if send_flush:
                    await send_flush()
                total_len = len("".join(buffer))
                elapsed = time.monotonic() - t_pipeline_start
                log_llm_done(conn_id, total_len, llm_chunk_count, elapsed)
                if voice_timings:
                    voice_timings.add("LLM done", f"chars={total_len} chunks={llm_chunk_count}")
                logger.info("[pipeline] LLM done sentences=%d total_len=%d", n_sentences, total_len)
            except Exception as e:
                logger.exception("[pipeline] LLM error: %s", e)
                raise

        # Coalesce small TTS chunks into ~4KB sends to reduce WebSocket frames and client stutter
        TTS_SEND_CHUNK_SIZE = 4096
        audio_buf = bytearray()

        async def relay_audio():
            n_relayed = 0
            total_bytes = 0
            t_first_audio = None
            nonlocal audio_buf
            try:
                async for chunk in receive_audio():
                    if chunk:
                        if t_first_audio is None:
                            t_first_audio = time.monotonic()
                            if voice_timings:
                                voice_timings.add("TTS out", "first audio chunk")
                        total_bytes += len(chunk)
                        audio_buf.extend(chunk)
                        while len(audio_buf) >= TTS_SEND_CHUNK_SIZE:
                            to_send = bytes(audio_buf[:TTS_SEND_CHUNK_SIZE])
                            del audio_buf[:TTS_SEND_CHUNK_SIZE]
                            on_audio_chunk(to_send)
                            n_relayed += 1
                            elapsed = time.monotonic() - t_pipeline_start
                            log_tts_audio_chunk(
                                conn_id, n_relayed, len(to_send), elapsed,
                                emit_rich=(n_relayed <= 3 or n_relayed % 10 == 1),
                            )
                if audio_buf:
                    on_audio_chunk(bytes(audio_buf))
                    n_relayed += 1
                    audio_buf.clear()
                elapsed = time.monotonic() - t_pipeline_start
                log_tts_flushed(conn_id, n_relayed, total_bytes, elapsed)
                if voice_timings:
                    voice_timings.add("TTS done", f"chunks={n_relayed} bytes={total_bytes}")
                logger.debug("[pipeline] relay_audio done chunks=%d", n_relayed)
            except asyncio.CancelledError:
                logger.debug("[pipeline] relay_audio cancelled after chunks=%d", n_relayed)
            except Exception as e:
                logger.warning("[pipeline] relay_audio ended: %s (chunks=%d)", e, n_relayed)

        audio_task = asyncio.create_task(relay_audio())
        await consume_llm_and_push_sentences()
        # Wait for TTS audio to finish (Deepgram sends audio then Flushed; relay_audio exits then).
        try:
            await asyncio.wait_for(audio_task, timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning("[pipeline] TTS relay timed out after 60s")
            audio_task.cancel()
            try:
                await audio_task
            except asyncio.CancelledError:
                pass
        if voice_timings:
            voice_timings.add("Pipeline", "done")
            log_turn_summary(voice_timings)
        logger.info("[pipeline] done (Deepgram TTS WS)")
        return

    # Non-Deepgram: buffer full reply, then REST TTS.
    await consume_llm()
    full_reply = "".join(buffer)
    if not full_reply.strip():
        logger.info("[pipeline] empty reply, skip TTS")
        return
    logger.info("[pipeline] REST TTS reply_len=%d", len(full_reply))
    provider = get_tts_provider()
    async for chunk in provider.stream_tts(full_reply):
        if chunk:
            on_audio_chunk(chunk)
    logger.info("[pipeline] done (REST TTS)")
