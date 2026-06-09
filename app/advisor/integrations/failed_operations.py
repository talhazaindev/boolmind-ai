"""Queue failed external operations for retry."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_memory_queue: list[dict[str, Any]] = []


async def queue_failed_operation(
    operation: str,
    payload: dict[str, Any],
    error: str,
) -> None:
    record = {
        "operation": operation,
        "payload": payload,
        "error": error[:500],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retries": 0,
    }
    _memory_queue.append(record)
    logger.warning("Queued failed operation %s: %s", operation, error[:120])

    if settings.supabase_configured:
        try:
            from app.advisor.integrations.supabase_client import insert_failed_operation

            await insert_failed_operation(record)
        except Exception as e:
            logger.debug("Supabase failed_ops insert skipped: %s", e)


def get_memory_queue() -> list[dict[str, Any]]:
    return list(_memory_queue)


def clear_memory_queue() -> None:
    _memory_queue.clear()
