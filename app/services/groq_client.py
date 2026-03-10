"""Groq LLM client for chat completions with streaming support."""

import logging
from typing import AsyncIterator, Optional

from groq import AsyncGroq

from app.core.config import settings

logger = logging.getLogger(__name__)


class GroqClientError(Exception):
    """Raised when Groq API calls fail."""

    pass


class GroqClient:
    """Async Groq client for chat completions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self._api_key = api_key or settings.groq_api_key
        self._model = model or settings.groq_model
        self._temperature = temperature if temperature is not None else settings.groq_temperature
        self._max_tokens = max_tokens or settings.groq_max_tokens
        self._client: Optional[AsyncGroq] = None

    def _get_client(self) -> AsyncGroq:
        if not self._api_key:
            raise GroqClientError("GROQ_API_KEY is not set")
        if self._client is None:
            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt_override: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream chat completion chunks. If system_prompt_override is provided,
        it is prepended as a system message (first message) when not already present.
        """
        client = self._get_client()
        if system_prompt_override and (
            not messages or messages[0].get("role") != "system"
        ):
            messages = [{"role": "system", "content": system_prompt_override}] + messages
        elif system_prompt_override and messages[0].get("role") == "system":
            messages = [
                {"role": "system", "content": system_prompt_override + "\n\n" + messages[0].get("content", "")}
            ] + messages[1:]

        try:
            stream = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.exception("Groq stream_chat failed: %s", e)
            raise GroqClientError(str(e)) from e
