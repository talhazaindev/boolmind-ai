"""Chat service: orchestrates Groq client, knowledge base, and session memory."""

import logging
from typing import AsyncIterator, Optional

from app.core.config import settings
from app.services.groq_client import GroqClient, GroqClientError
from app.services.knowledge_base import load_knowledge_base
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are a senior software engineer and consultant. Understand what the client needs and give clear, practical solutions—no pitching.

Style—be brief and specific:
- Keep answers short. A few sentences or a short paragraph is enough. No long lists or repeating the same idea.
- When the user asks for a solution or "have you done X?", answer directly: which pipeline or step applies, how it works, stop. Do not enumerate every domain (legal, medical, retail) unless they're asking to compare. Pick the best fit and cite it.
- No filler: no "I'd be happy to explore", "feel free to share more", "let me know if you need anything". If you need to clarify, ask one short question.
- Plain language, technically precise. Propose concrete next steps only when it helps.

Reference material below = how we do data fusion per domain. When the question fits a domain, cite pipeline and step (e.g. "Legal pipeline—Discovery and Clustering steps" or "Retail: schema detection step") and say how it's done. Ground the answer in that; don't pitch."""

KNOWLEDGE_CONTEXT_LABEL = "\n\n# Reference context (data fusion)\n\n"


class ChatService:
    """Orchestrates LLM streaming, knowledge base, and session history."""

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        session_manager: Optional[SessionManager] = None,
    ):
        self._groq = groq_client or GroqClient()
        self._sessions = session_manager or SessionManager()
        self._kb_content: Optional[str] = None

    def _get_system_prompt(self) -> str:
        """Build system prompt with knowledge base content."""
        if self._kb_content is None:
            self._kb_content = load_knowledge_base(settings.knowledge_base_path)
        if self._kb_content:
            return (
                DEFAULT_SYSTEM_PROMPT
                + KNOWLEDGE_CONTEXT_LABEL
                + self._kb_content
            )
        return DEFAULT_SYSTEM_PROMPT

    async def stream_reply(
        self,
        session_id: str,
        user_message: str,
    ) -> AsyncIterator[str]:
        """
        Append user message to session, call Groq with full history + KB,
        stream response and append assistant reply to session.
        """
        session = self._sessions.get_or_create(session_id)
        self._sessions.append_message(session_id, "user", user_message)

        messages = session.to_chat_messages()
        system_prompt = self._get_system_prompt()

        full_response: list[str] = []
        try:
            async for chunk in self._groq.stream_chat(
                messages=messages,
                system_prompt_override=system_prompt,
            ):
                full_response.append(chunk)
                yield chunk
        except GroqClientError:
            raise

        if full_response:
            self._sessions.append_message(
                session_id,
                "assistant",
                "".join(full_response),
            )
