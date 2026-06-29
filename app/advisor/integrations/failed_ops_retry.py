"""Replay failed external operations."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.advisor.integrations.failed_operations import remove_from_memory_queue
from app.advisor.monitoring.telemetry import emit
from app.advisor.tools import calendar_book_slot, crm_create_lead, send_meeting_invite
from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5

_DISPATCHERS: dict[str, str] = {
    "calendar_book_slot": "calendar_book_slot",
    "send_meeting_invite": "send_meeting_invite",
    "crm_create_lead": "crm_create_lead",
}


def _item_key(operation: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"operation": operation, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_supabase_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    return {
        "id": row.get("id"),
        "source": "supabase",
        "operation": row.get("operation", ""),
        "payload": payload if isinstance(payload, dict) else {},
        "error": row.get("error_message", ""),
        "retries": int(row.get("retries", 0)),
        "session_id": session_id,
        "created_at": row.get("created_at"),
    }


async def replay_failed_operation(item: dict[str, Any]) -> dict[str, Any]:
    """Attempt to replay a single failed operation. Returns outcome dict."""
    operation = item.get("operation", "")
    payload = item.get("payload") or {}
    session_id = item.get("session_id") or payload.get("session_id") or "retry-worker"
    retries = int(item.get("retries", 0))

    if retries >= _MAX_RETRIES:
        return {"operation": operation, "outcome": "max_retries", "success": False}

    try:
        if operation == "calendar_book_slot":
            result = await calendar_book_slot.handle(payload)
            success = result.get("status") in ("booked", "queued")
        elif operation == "send_meeting_invite":
            result = await send_meeting_invite.handle(payload)
            success = result.get("status") in ("sent", "skipped", "queued")
        elif operation == "crm_create_lead":
            result = await crm_create_lead.handle(
                payload,
                session_id,
                payload.get("visitor_id"),
            )
            success = result.get("status") in ("created", "queued", "duplicate")
        else:
            return {"operation": operation, "outcome": "unknown_operation", "success": False}

        outcome = "success" if success else "failed"
        await emit(
            "failed_operation_retried",
            session_id,
            metadata={
                "operation": operation,
                "retry_count": retries + 1,
                "outcome": outcome,
                "source": item.get("source", "memory"),
            },
        )
        return {"operation": operation, "outcome": outcome, "success": success, "result": result}
    except Exception as e:
        logger.exception("Replay failed for %s: %s", operation, e)
        await emit(
            "failed_operation_retried",
            session_id,
            metadata={
                "operation": operation,
                "retry_count": retries + 1,
                "outcome": "error",
                "error_class": type(e).__name__,
                "source": item.get("source", "memory"),
            },
            exception=e,
        )
        return {
            "operation": operation,
            "outcome": "error",
            "success": False,
            "error": str(e)[:200],
        }


async def replay_memory_queue() -> dict[str, Any]:
    """Replay all eligible items in the in-memory failed-ops queue."""
    from app.advisor.integrations.failed_operations import get_memory_queue

    queue = get_memory_queue()
    results: list[dict[str, Any]] = []
    to_remove: list[int] = []

    for idx, item in enumerate(queue):
        if item.get("retries", 0) >= _MAX_RETRIES:
            continue
        item = {**item, "source": "memory"}
        item["retries"] = item.get("retries", 0) + 1
        outcome = await replay_failed_operation(item)
        results.append(outcome)
        if outcome.get("success"):
            to_remove.append(idx)

    for idx in reversed(to_remove):
        remove_from_memory_queue(idx)

    remaining = len(get_memory_queue())
    return {
        "retried": len(results),
        "succeeded": sum(1 for r in results if r.get("success")),
        "pending": remaining,
        "results": results,
    }


async def replay_supabase_queue() -> dict[str, Any]:
    """Replay pending failed operations stored in Supabase."""
    if not settings.supabase_configured:
        return {"retried": 0, "succeeded": 0, "pending": 0, "results": []}

    from app.advisor.integrations.supabase_client import (
        fetch_failed_operations,
        update_failed_operation_retries,
    )

    rows = await fetch_failed_operations()
    results: list[dict[str, Any]] = []
    succeeded = 0

    for row in rows:
        item = _normalize_supabase_row(row)
        op_id = item.get("id")
        if not op_id or item.get("retries", 0) >= _MAX_RETRIES:
            continue
        new_retries = item.get("retries", 0) + 1
        await update_failed_operation_retries(str(op_id), new_retries)
        item["retries"] = new_retries
        outcome = await replay_failed_operation(item)
        results.append(outcome)
        if outcome.get("success"):
            succeeded += 1
            await update_failed_operation_retries(str(op_id), _MAX_RETRIES)
        elif new_retries >= _MAX_RETRIES:
            await update_failed_operation_retries(str(op_id), _MAX_RETRIES)

    remaining_rows = await fetch_failed_operations()
    return {
        "retried": len(results),
        "succeeded": succeeded,
        "pending": len(remaining_rows),
        "results": results,
    }


async def replay_all_queues() -> dict[str, Any]:
    """Replay in-memory and Supabase failed-operation queues."""
    memory_result = await replay_memory_queue()
    supabase_result = await replay_supabase_queue()
    return {
        "retried": memory_result["retried"] + supabase_result["retried"],
        "succeeded": memory_result["succeeded"] + supabase_result["succeeded"],
        "pending": memory_result["pending"] + supabase_result["pending"],
        "memory": memory_result,
        "supabase": supabase_result,
        "results": memory_result["results"] + supabase_result["results"],
    }
