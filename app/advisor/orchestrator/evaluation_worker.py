"""Background evaluate_turn — off critical path."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.advisor.integrations.redis_store import RedisSessionStore
from app.advisor.orchestrator.conversation_evaluator import evaluate_turn
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.orchestrator.session_metadata import persist_discovery_evaluation
from app.advisor.types import PageContext, SessionMetadata

logger = logging.getLogger(__name__)


async def _run_evaluation_job(
    redis: RedisSessionStore,
    session_id: str,
    visitor_id: str | None,
    user_message: str,
    history: list[dict[str, Any]],
    profile_snapshot: SessionMetadata,
    product_context: ProductContext,
    page_context: PageContext,
) -> None:
    try:
        evaluation = await evaluate_turn(
            session_id=session_id,
            user_message=user_message,
            history=history,
            profile=profile_snapshot,
            product_context=product_context,
            page_context=page_context,
        )
        await persist_discovery_evaluation(
            redis,
            visitor_id,
            profile_snapshot,
            stage=evaluation.stage,
            profile_updates=evaluation.profile_updates,
            missing_fields=evaluation.missing_fields,
            llm_readiness=evaluation.readiness,
            user_sophistication=evaluation.user_sophistication,
        )
    except Exception as e:
        logger.warning("background evaluate_turn failed session=%s: %s", session_id, e)


def enqueue_evaluation(
    redis: RedisSessionStore,
    session_id: str,
    visitor_id: str | None,
    user_message: str,
    history: list[dict[str, Any]],
    profile_snapshot: SessionMetadata,
    product_context: ProductContext,
    page_context: PageContext,
) -> None:
    """Fire-and-forget background evaluation for turn N+1 profile merge."""
    asyncio.create_task(
        _run_evaluation_job(
            redis,
            session_id,
            visitor_id,
            user_message,
            history,
            profile_snapshot.model_copy(deep=True),
            product_context,
            page_context,
        )
    )
