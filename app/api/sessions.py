"""Session API: create and retrieve conversation sessions."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import SessionManagerDep
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionResponse(BaseModel):
    """Response after creating a new session."""

    session_id: str
    created_at: str


class MessageOut(BaseModel):
    """Message in API response."""

    role: str
    content: str


class SessionResponse(BaseModel):
    """Session with conversation history."""

    session_id: str
    created_at: str
    updated_at: str
    messages: list[MessageOut]


@router.post("/new", response_model=CreateSessionResponse)
async def create_session(
    sessions: SessionManagerDep,
    session_id: str | None = None,
) -> CreateSessionResponse:
    """Create a new chat session. Optionally provide session_id as query param."""
    try:
        session = sessions.create_session(session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return CreateSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at.isoformat() + "Z",
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    sessions: SessionManagerDep,
) -> SessionResponse:
    """Retrieve conversation history for a session."""
    session = sessions.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at.isoformat() + "Z",
        updated_at=session.updated_at.isoformat() + "Z",
        messages=[MessageOut(role=m.role, content=m.content) for m in session.messages],
    )
