"""Voice API: TTS (streaming speak). STT is done in the browser via Web Speech API (webkit)."""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.stt import get_stt_provider
from app.services.tts import TTSStreamError, get_tts_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


def _tts_provider():
    return get_tts_provider()


@router.get("/tts-status")
async def voice_tts_status() -> JSONResponse:
    """Returns whether the configured TTS provider is available. Frontend can disable Speak when false."""
    try:
        await _tts_provider().check_available()
        return JSONResponse(content={"available": True})
    except TTSStreamError as e:
        return JSONResponse(
            status_code=503,
            content={"available": False, "detail": str(e)},
        )


@router.post("/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> JSONResponse:
    """
    Transcribe audio using server-side STT when STT_PROVIDER=deepgram.
    Accepts multipart file upload. Returns {"text": "..."}.
    When STT is webkit (no server STT), returns 410.
    """
    stt_provider = get_stt_provider()
    if stt_provider is None:
        return JSONResponse(
            status_code=410,
            content={
                "detail": "Server-side transcribe not configured. Set STT_PROVIDER=deepgram and DEEPGRAM_API_KEY.",
                "text": "",
            },
        )
    try:
        await stt_provider.check_available()
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"detail": str(e), "text": ""},
        )
    try:
        from deepgram import AsyncDeepgramClient
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"detail": "Deepgram SDK not installed.", "text": ""},
        )
    body = await file.read()
    if not body:
        return JSONResponse(content={"text": ""})
    client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)
    try:
        response = await client.listen.v1.media.transcribe_file(
            request=body,
            model=settings.deepgram_stt_model or "nova-2",
        )
    except Exception as e:
        logger.exception("Deepgram transcribe_file: %s", e)
        return JSONResponse(
            status_code=502,
            content={"detail": str(e), "text": ""},
        )
    text = ""
    if getattr(response, "results", None) and getattr(response.results, "channels", None):
        channels = response.results.channels
        if channels and getattr(channels[0], "alternatives", None):
            alts = channels[0].alternatives
            if alts and getattr(alts[0], "transcript", None):
                text = (alts[0].transcript or "").strip()
    return JSONResponse(content={"text": text})


class SpeakRequest(BaseModel):
    """Request body for TTS."""

    text: str = Field(..., min_length=1)
    streaming_quality: str = "balanced"
    streaming_strategy: str = "sentence"
    streaming_chunk_size: int = 200


@router.post("/speak")
async def voice_speak(body: SpeakRequest) -> StreamingResponse:
    """Stream TTS audio from the configured provider (Chatterbox or ElevenLabs)."""
    provider = _tts_provider()
    try:
        await provider.check_available()
    except TTSStreamError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    async def generate():
        try:
            async for chunk in provider.stream_tts(
                body.text,
                streaming_quality=body.streaming_quality,
                streaming_strategy=body.streaming_strategy,
                streaming_chunk_size=body.streaming_chunk_size,
            ):
                yield chunk
        except TTSStreamError as e:
            logger.exception("TTS stream failed: %s", e)
            raise

    return StreamingResponse(
        generate(),
        media_type=provider.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
