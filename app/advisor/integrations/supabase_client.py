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
