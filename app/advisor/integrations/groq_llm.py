"""Groq LLM client with API key rotation and rate-limit failover."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from typing import Any

from groq import AsyncGroq, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_rate_limit_error(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg


class GroqKeyRotator:
    """Round-robin across multiple Groq API keys; retry next key on 429."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("At least one Groq API key is required")
        self._keys = keys
        self._lock = threading.Lock()
        self._index = 0
        self._clients: dict[str, AsyncGroq] = {}

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def next_key(self) -> str:
        with self._lock:
            key = self._keys[self._index % len(self._keys)]
            self._index += 1
            return key

    def client_for_key(self, api_key: str) -> AsyncGroq:
        if api_key not in self._clients:
            self._clients[api_key] = AsyncGroq(api_key=api_key)
        return self._clients[api_key]

    async def create_chat_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = "auto",
    ) -> Any:
        """Create streaming completion; rotate keys on rate limit."""
        last_error: BaseException | None = None
        cooldown_s = 30
        max_passes = 2

        for pass_idx in range(max_passes):
            tried: set[str] = set()
            while len(tried) < len(self._keys):
                api_key = self.next_key()
                if api_key in tried:
                    continue
                tried.add(api_key)
                client = self.client_for_key(api_key)
                try:
                    kwargs: dict[str, Any] = {
                        "model": settings.groq_model,
                        "messages": messages,
                        "temperature": settings.groq_temperature,
                        "max_tokens": settings.groq_max_tokens,
                        "stream": True,
                    }
                    if tools is not None:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = tool_choice
                    return await client.chat.completions.create(**kwargs)
                except Exception as e:
                    if _is_rate_limit_error(e):
                        last_error = e
                        logger.warning(
                            "Groq rate limit on key …%s, rotating (%d/%d keys tried)",
                            api_key[-6:],
                            len(tried),
                            len(self._keys),
                        )
                        continue
                    raise

            if pass_idx < max_passes - 1:
                logger.warning(
                    "Groq: all keys rate limited; cooling down %ds before retry",
                    cooldown_s,
                )
                await asyncio.sleep(cooldown_s)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Groq: all API keys exhausted")

    async def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> str:
        """Non-streaming completion for structured evaluator calls."""
        last_error: BaseException | None = None
        tried: set[str] = set()
        resolved_model = model or settings.groq_eval_model_resolved

        while len(tried) < len(self._keys):
            api_key = self.next_key()
            if api_key in tried:
                continue
            tried.add(api_key)
            client = self.client_for_key(api_key)
            try:
                kwargs: dict[str, Any] = {
                    "model": resolved_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format
                response = await client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                return content.strip()
            except Exception as e:
                if _is_rate_limit_error(e):
                    last_error = e
                    logger.warning(
                        "Groq eval rate limit on key …%s, rotating",
                        api_key[-6:],
                    )
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Groq: all API keys exhausted")


_rotator: GroqKeyRotator | None = None


def get_groq_rotator() -> GroqKeyRotator:
    global _rotator
    if _rotator is None:
        keys = settings.get_groq_api_keys()
        _rotator = GroqKeyRotator(keys)
        logger.info("Groq key pool initialized with %d key(s)", len(keys))
    return _rotator


def reset_groq_rotator() -> None:
    """Reset pool (for tests)."""
    global _rotator
    _rotator = None


# Backward-compatible alias
def get_groq_client() -> GroqKeyRotator:
    return get_groq_rotator()
