"""Redis session store — Upstash (REST) or local Redis (Docker / dev)."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.advisor.constants import HISTORY_TTL_SECONDS, MAX_HISTORY_MESSAGES, VISITOR_TTL_SECONDS
from app.advisor.types import ChatMessage, SessionMetadata
from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    """Conversation history and visitor metadata."""

    async def get_history(self, session_id: str) -> list[dict[str, Any]]: ...

    async def append_history(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        tool_messages: list[dict[str, Any]] | None = None,
    ) -> None: ...

    async def get_visitor_metadata(self, visitor_id: str) -> SessionMetadata | None: ...

    async def save_visitor_metadata(self, visitor_id: str, meta: SessionMetadata) -> None: ...

    async def clear_history(self, session_id: str) -> None: ...

    async def ping(self) -> bool: ...


class UpstashRedisSessionStore:
    """Conversation history and visitor metadata in Upstash Redis (REST)."""

    def __init__(self) -> None:
        if not settings.upstash_configured:
            raise RuntimeError("Upstash Redis is not configured")
        from upstash_redis import Redis

        self._redis = Redis(
            url=settings.upstash_redis_rest_url.strip().strip('"'),
            token=settings.upstash_redis_rest_token.strip().strip('"'),
        )

    def _history_key(self, session_id: str) -> str:
        return f"history:{session_id}"

    def _visitor_key(self, visitor_id: str) -> str:
        return f"session:{visitor_id}"

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        raw = self._redis.get(self._history_key(session_id))
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []

    async def append_history(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        tool_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        history = await self.get_history(session_id)
        history.append({"role": "user", "content": user_content})
        if tool_messages:
            history.extend(tool_messages)
        history.append({"role": "assistant", "content": assistant_content})
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        self._redis.set(
            self._history_key(session_id),
            json.dumps(history),
            ex=HISTORY_TTL_SECONDS,
        )

    async def get_visitor_metadata(self, visitor_id: str) -> SessionMetadata | None:
        raw = self._redis.get(self._visitor_key(visitor_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw) if isinstance(raw, str) else raw
        return SessionMetadata.model_validate(data)

    async def save_visitor_metadata(self, visitor_id: str, meta: SessionMetadata) -> None:
        self._redis.set(
            self._visitor_key(visitor_id),
            meta.model_dump_json(),
            ex=VISITOR_TTL_SECONDS,
        )

    async def clear_history(self, session_id: str) -> None:
        self._redis.delete(self._history_key(session_id))

    async def ping(self) -> bool:
        try:
            return self._redis.ping() is True or self._redis.get("boolmind:ping") is not None
        except Exception:
            self._redis.set("boolmind:ping", "1", ex=60)
            return True


class LocalRedisSessionStore:
    """Conversation history and visitor metadata in a standard Redis instance."""

    def __init__(self) -> None:
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL is not configured")
        import redis

        self._redis = redis.Redis.from_url(
            settings.redis_url.strip(),
            decode_responses=True,
        )

    def _history_key(self, session_id: str) -> str:
        return f"history:{session_id}"

    def _visitor_key(self, visitor_id: str) -> str:
        return f"session:{visitor_id}"

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        raw = self._redis.get(self._history_key(session_id))
        if not raw:
            return []
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []

    async def append_history(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        tool_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        history = await self.get_history(session_id)
        history.append({"role": "user", "content": user_content})
        if tool_messages:
            history.extend(tool_messages)
        history.append({"role": "assistant", "content": assistant_content})
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        self._redis.set(
            self._history_key(session_id),
            json.dumps(history),
            ex=HISTORY_TTL_SECONDS,
        )

    async def get_visitor_metadata(self, visitor_id: str) -> SessionMetadata | None:
        raw = self._redis.get(self._visitor_key(visitor_id))
        if not raw:
            return None
        data = json.loads(raw) if isinstance(raw, str) else raw
        return SessionMetadata.model_validate(data)

    async def save_visitor_metadata(self, visitor_id: str, meta: SessionMetadata) -> None:
        self._redis.set(
            self._visitor_key(visitor_id),
            meta.model_dump_json(),
            ex=VISITOR_TTL_SECONDS,
        )

    async def clear_history(self, session_id: str) -> None:
        self._redis.delete(self._history_key(session_id))

    async def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False


# Backward-compatible alias
RedisSessionStore = UpstashRedisSessionStore

_store: SessionStore | None = None


def get_redis_store() -> SessionStore:
    global _store
    if _store is None:
        backend = settings.redis_backend.strip().lower()
        if backend == "local":
            _store = LocalRedisSessionStore()
            logger.info("Session store: local Redis (%s)", settings.redis_url)
        elif backend == "upstash":
            _store = UpstashRedisSessionStore()
            logger.info("Session store: Upstash Redis")
        else:
            raise RuntimeError(f"Unsupported REDIS_BACKEND: {settings.redis_backend}")
    return _store
