"""LLM client for chat completions with streaming support."""

import logging
from typing import AsyncIterator, Optional

from groq import AsyncGroq

from app.advisor.integrations.groq_llm import (
    GroqKeyRotator,
    _is_rate_limit_error,
    get_chat_llm_client,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class GroqClientError(Exception):
    """Raised when LLM API calls fail."""

    pass


class GroqClient:
    """Async LLM client for chat completions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        keys = settings.get_groq_api_keys()
        self._api_key = api_key or (keys[0] if keys else "")
        self._model = model or settings.llm_model_resolved
        self._temperature = temperature if temperature is not None else settings.groq_temperature
        self._max_tokens = max_tokens or settings.groq_max_tokens
        self._use_pool = (
            api_key is None
            and settings.llm_provider_resolved == "groq"
            and len(keys) > 1
        )

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt_override: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream chat completion chunks. If system_prompt_override is provided,
        it is prepended as a system message (first message) when not already present.
        """
        if not self._api_key and not settings.llm_configured:
            raise GroqClientError("LLM is not configured (set GROQ_API_KEY or LLM_PROVIDER=ollama)")

        if system_prompt_override and (
            not messages or messages[0].get("role") != "system"
        ):
            messages = [{"role": "system", "content": system_prompt_override}] + messages
        elif system_prompt_override and messages[0].get("role") == "system":
            messages = [
                {"role": "system", "content": system_prompt_override + "\n\n" + messages[0].get("content", "")}
            ] + messages[1:]

        try:
            if settings.llm_provider_resolved == "ollama":
                stream = await get_chat_llm_client().create_chat_stream(messages=messages, tools=None)
            elif self._use_pool:
                client = get_chat_llm_client()
                if not isinstance(client, GroqKeyRotator):
                    raise GroqClientError("Expected Groq key rotator")
                stream = await client.create_chat_stream(messages=messages, tools=None)
            else:
                client = AsyncGroq(api_key=self._api_key)
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
            if _is_rate_limit_error(e):
                raise GroqClientError(
                    "Groq rate limit reached on all configured API keys. Please retry shortly."
                ) from e
            logger.exception("LLM stream_chat failed: %s", e)
            raise GroqClientError(str(e)) from e
