"""Lightweight connectivity probes for external integrations."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

HealthStatus = dict[str, Any]
_CACHE_TTL_S = 30.0
_cache: dict[str, Any] | None = None
_cache_at: float = 0.0


def _status(configured: bool, reachable: bool, error: str | None = None) -> HealthStatus:
    if not configured:
        return {"configured": False, "reachable": False, "status": "OFF", "error": None}
    if reachable:
        return {"configured": True, "reachable": True, "status": "ON", "error": None}
    return {"configured": True, "reachable": False, "status": "DEGRADED", "error": error}


async def check_supabase() -> HealthStatus:
    if not settings.supabase_configured:
        return _status(False, False)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/chat_events",
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Accept": "application/json",
                },
                params={"select": "id", "limit": "1"},
            )
        ok = resp.status_code in (200, 206)
        return _status(True, ok, None if ok else resp.text[:120])
    except Exception as e:
        logger.debug("supabase health failed: %s", e)
        return _status(True, False, str(e)[:120])


async def check_hubspot() -> HealthStatus:
    if not settings.hubspot_configured:
        return _status(False, False)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.hubapi.com/crm/v3/objects/contacts",
                headers={"Authorization": f"Bearer {settings.hubspot_access_token}"},
                params={"limit": "1"},
            )
        ok = resp.status_code in (200, 207)
        return _status(True, ok, None if ok else resp.text[:120])
    except Exception as e:
        logger.debug("hubspot health failed: %s", e)
        return _status(True, False, str(e)[:120])


async def check_calcom() -> HealthStatus:
    if not settings.calcom_configured:
        return _status(False, False)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://api.cal.com/v2/event-types/{settings.calcom_event_type_id}",
                headers={
                    "Authorization": f"Bearer {settings.calcom_api_key}",
                    "cal-api-version": "2024-06-14",
                },
            )
        ok = resp.status_code == 200
        return _status(True, ok, None if ok else resp.text[:120])
    except Exception as e:
        logger.debug("calcom health failed: %s", e)
        return _status(True, False, str(e)[:120])


async def check_resend() -> HealthStatus:
    if not settings.resend_configured:
        return _status(False, False)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        ok = resp.status_code == 200 or (
            resp.status_code == 401 and "restricted_api_key" in resp.text
        )
        return _status(True, ok, None if ok else resp.text[:120])
    except Exception as e:
        logger.debug("resend health failed: %s", e)
        return _status(True, False, str(e)[:120])


async def check_posthog() -> HealthStatus:
    if not settings.posthog_configured:
        return _status(False, False)
    try:
        from app.advisor.analytics import events as analytics

        analytics.capture(
            "$health_check",
            "health-probe",
            {"source": "advisor-admin", "configured": True},
        )
        return _status(True, True)
    except Exception as e:
        logger.debug("posthog health failed: %s", e)
        return _status(True, False, str(e)[:120])


async def check_sentry() -> HealthStatus:
    if not settings.sentry_configured:
        return _status(False, False)
    try:
        import sentry_sdk

        sentry_sdk.capture_message("advisor health probe", level="info")
        return _status(True, True)
    except Exception as e:
        logger.debug("sentry health failed: %s", e)
        return _status(True, False, str(e)[:120])


async def check_all() -> dict[str, HealthStatus]:
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL_S:
        return _cache
    _cache = {
        "supabase": await check_supabase(),
        "hubspot": await check_hubspot(),
        "calcom": await check_calcom(),
        "resend": await check_resend(),
        "posthog": await check_posthog(),
        "sentry": await check_sentry(),
    }
    _cache_at = now
    return _cache
