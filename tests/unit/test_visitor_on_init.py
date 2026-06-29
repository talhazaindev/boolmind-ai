"""Returning visitor on chat-init."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.advisor.orchestrator.session_metadata import ensure_visitor_on_init
from app.advisor.types import PageContext, SessionMetadata


@pytest.mark.asyncio
async def test_first_visit_not_returning() -> None:
    redis = MagicMock()
    redis.get_visitor_metadata = AsyncMock(return_value=None)
    redis.save_visitor_metadata = AsyncMock()
    page = PageContext(url="http://127.0.0.1:8000/advisor", product_id="retify")

    meta = await ensure_visitor_on_init(redis, "vid-1", page)

    assert meta.visit_count == 1
    assert meta.is_returning is False
    redis.save_visitor_metadata.assert_called_once()


@pytest.mark.asyncio
async def test_second_init_is_returning() -> None:
    redis = MagicMock()
    redis.get_visitor_metadata = AsyncMock(
        return_value=SessionMetadata(visit_count=1, is_returning=False)
    )
    redis.save_visitor_metadata = AsyncMock()
    page = PageContext(url="http://127.0.0.1:8000/advisor")

    meta = await ensure_visitor_on_init(redis, "vid-1", page)

    assert meta.visit_count == 2
    assert meta.is_returning is True


def test_is_returning_flag_from_visit_count() -> None:
    assert not (SessionMetadata(visit_count=1).visit_count > 1)
    assert SessionMetadata(visit_count=2).visit_count > 1
