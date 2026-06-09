"""Chat clear API helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.advisor.integrations.redis_store import RedisSessionStore
from app.advisor.orchestrator.session_metadata import clear_visitor_conversation_context
from app.advisor.types import SessionMetadata


@pytest.mark.asyncio
async def test_clear_history_deletes_key() -> None:
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._redis = MagicMock()
    await store.clear_history("sess-123")
    store._redis.delete.assert_called_once_with("history:sess-123")


@pytest.mark.asyncio
async def test_clear_visitor_conversation_context_resets_fields() -> None:
    redis = MagicMock()
    meta = SessionMetadata(
        visitor_name="Ada",
        last_topic="Retify pricing",
        products_discussed=["retify"],
        active_product="retify",
        collected_email="ada@example.com",
    )
    redis.get_visitor_metadata = AsyncMock(return_value=meta)
    redis.save_visitor_metadata = AsyncMock()
    await clear_visitor_conversation_context(redis, "vid-1")
    saved = redis.save_visitor_metadata.call_args[0][1]
    assert saved.last_topic is None
    assert saved.products_discussed == []
    assert saved.active_product is None
    assert saved.visitor_name == "Ada"
    assert saved.collected_email == "ada@example.com"
