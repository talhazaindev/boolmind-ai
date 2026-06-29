"""Session store backend selection."""

from __future__ import annotations

from unittest.mock import patch

from app.core.config import Settings


def test_redis_configured_local() -> None:
    s = Settings(
        redis_backend="local",
        redis_url="redis://localhost:6379/0",
    )
    assert s.redis_configured is True


def test_redis_configured_upstash() -> None:
    s = Settings(
        redis_backend="upstash",
        upstash_redis_rest_url="https://example.upstash.io",
        upstash_redis_rest_token="token",
    )
    assert s.redis_configured is True


def test_pinecone_configured_local() -> None:
    s = Settings(
        pinecone_mode="local",
        pinecone_host="pinecone",
        pinecone_index_name="boolmind-knowledge-bge",
    )
    assert s.pinecone_configured is True


def test_get_redis_store_selects_local() -> None:
    import app.advisor.integrations.redis_store as mod

    mod._store = None
    with patch("app.advisor.integrations.redis_store.settings") as mock_settings, patch.object(
        mod, "LocalRedisSessionStore"
    ) as mock_local:
        mock_settings.redis_backend = "local"
        mock_settings.redis_url = "redis://localhost:6379/0"
        store = mod.get_redis_store()
        mock_local.assert_called_once()
        assert store is mock_local.return_value
    mod._store = None
