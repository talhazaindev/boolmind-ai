"""Chat API: streaming endpoint with session support."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.dependencies import SessionManagerDep
from app.services.chat_service import ChatService
from app.services.groq_client import GroqClientError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatStreamRequest(BaseModel):
    """Request body for streaming chat."""

    message: str = Field(..., min_length=1, description="User message")
    session_id: str = Field(..., min_length=1, description="Session ID for conversation memory")


async def stream_generator(session_id: str, message: str, sessions: SessionManagerDep):
    """Async generator yielding SSE events for chat stream."""
    service = ChatService(session_manager=sessions)
    try:
        async for chunk in service.stream_reply(session_id=session_id, user_message=message):
            yield {"data": chunk}
    except GroqClientError as e:
        logger.exception("Chat stream error: %s", e)
        yield {"event": "error", "data": str(e)}


@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    sessions: SessionManagerDep,
):
    """
    Streaming chat: send a message and receive SSE stream of assistant reply.
    Uses session_id for conversation history (creates session if missing).
    """
    return EventSourceResponse(
        stream_generator(
            session_id=body.session_id,
            message=body.message,
            sessions=sessions,
        )
    )
