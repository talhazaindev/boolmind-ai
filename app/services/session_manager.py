"""In-memory session manager for per-session conversation memory."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Message(BaseModel):
    """Single chat message in conversation history."""

    role: str = Field(..., description="user | assistant | system")
    content: str = Field(..., description="Message content")


class Session(BaseModel):
    """A chat session with conversation history."""

    session_id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    messages: list[Message] = Field(default_factory=list, description="Conversation history")

    def to_chat_messages(self) -> list[dict[str, str]]:
        """Format for Groq API: list of {role, content}."""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def append(self, role: str, content: str) -> None:
        """Append a message and refresh updated_at."""
        self.messages.append(Message(role=role, content=content))
        self.updated_at = datetime.utcnow()


class SessionManager:
    """
    In-memory session store. Replace with Redis or another backend
    for production multi-instance deployments.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self, session_id: Optional[str] = None) -> Session:
        """Create a new session. If session_id is None, generate a UUID."""
        sid = session_id or str(uuid.uuid4())
        if sid in self._sessions:
            raise ValueError(f"Session already exists: {sid}")
        session = Session(session_id=sid)
        self._sessions[sid] = session
        logger.info("Created session %s", sid)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Return session by id or None."""
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        """Get existing session or create one with the given id."""
        session = self.get_session(session_id)
        if session is not None:
            return session
        return self.create_session(session_id=session_id)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """Append a message to a session. Creates session if missing."""
        session = self.get_or_create(session_id)
        session.append(role=role, content=content)

    def list_sessions(self) -> list[Session]:
        """Return all sessions (for debugging/admin)."""
        return list(self._sessions.values())


def get_session_manager() -> SessionManager:
    """Dependency: single shared in-memory SessionManager."""
    if not hasattr(get_session_manager, "_instance"):
        get_session_manager._instance = SessionManager()
    return get_session_manager._instance
