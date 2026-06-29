"""Queue failed external operations for retry."""

from __future__ import annotations

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
    *,
    session_id: str | None = None,
) -> None:
    record = {
        "operation": operation,
        "payload": payload,
        "error": error[:500],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retries": 0,
        "session_id": session_id,
    }
    _memory_queue.append(record)
    logger.warning("Queued failed operation %s: %s", operation, error[:120])

    from app.advisor.monitoring.prometheus_metrics import set_failed_ops_pending
    from app.advisor.monitoring.telemetry import emit

    set_failed_ops_pending(len(_memory_queue))
    if session_id:
        await emit(
            "failed_operation_queued",
            session_id,
            metadata={"operation": operation, "error_type": error[:120]},
        )

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
    from app.advisor.monitoring.prometheus_metrics import set_failed_ops_pending

    set_failed_ops_pending(0)


def remove_from_memory_queue(index: int) -> None:
    if 0 <= index < len(_memory_queue):
        _memory_queue.pop(index)
    from app.advisor.monitoring.prometheus_metrics import set_failed_ops_pending

    set_failed_ops_pending(len(_memory_queue))
