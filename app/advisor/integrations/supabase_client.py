"""Supabase parameterized writes."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _rest_url(table: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}"


async def insert_row(table: str, row: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(_rest_url(table), headers=_headers(), json=row)
        if resp.status_code not in (200, 201, 204):
            logger.warning("Supabase insert %s: %s %s", table, resp.status_code, resp.text[:200])


async def insert_failed_operation(record: dict[str, Any]) -> None:
    await insert_row(
        "failed_operations",
        {
            "operation": record["operation"],
            "payload": record["payload"],
            "error_message": record["error"],
            "retries": record.get("retries", 0),
        },
    )


async def insert_lead(row: dict[str, Any]) -> None:
    await insert_row("leads", row)


async def insert_chat_event(row: dict[str, Any]) -> None:
    await insert_row("chat_events", row)


async def fetch_chat_events(session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch chat_events for a session (admin / test audit)."""
    if not settings.supabase_configured:
        return []
    params = {
        "session_id": f"eq.{session_id}",
        "order": "created_at.asc",
        "limit": str(limit),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            _rest_url("chat_events"),
            headers={**_headers(), "Accept": "application/json"},
            params=params,
        )
        if resp.status_code != 200:
            logger.warning("Supabase fetch chat_events: %s %s", resp.status_code, resp.text[:200])
            return []
        return resp.json()


async def fetch_failed_operations(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch pending failed operations from Supabase."""
    if not settings.supabase_configured:
        return []
    params = {
        "retries": "lt.5",
        "order": "created_at.desc",
        "limit": str(limit),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            _rest_url("failed_operations"),
            headers={**_headers(), "Accept": "application/json"},
            params=params,
        )
        if resp.status_code != 200:
            logger.warning(
                "Supabase fetch failed_operations: %s %s", resp.status_code, resp.text[:200]
            )
            return []
        return resp.json()


async def update_failed_operation_retries(op_id: str, retries: int) -> None:
    """Update retry count on a failed operation row."""
    if not settings.supabase_configured:
        return
    from datetime import datetime, timezone

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(
            f"{_rest_url('failed_operations')}?id=eq.{op_id}",
            headers=_headers(),
            json={
                "retries": retries,
                "last_retry_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if resp.status_code not in (200, 204):
            logger.warning("Supabase update failed_op: %s %s", resp.status_code, resp.text[:200])
