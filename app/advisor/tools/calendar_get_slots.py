"""Cal.com available slots."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    if not settings.calcom_configured:
        start = arguments.get("start_date") or datetime.utcnow().strftime("%Y-%m-%d")
        end = arguments.get("end_date") or (
            datetime.utcnow() + timedelta(days=7)
        ).strftime("%Y-%m-%d")
        return {
            "slots": [
                {"start": f"{start}T14:00:00Z", "end": f"{start}T14:30:00Z"},
                {"start": f"{start}T15:00:00Z", "end": f"{start}T15:30:00Z"},
            ],
            "timezone": arguments.get("timezone", settings.calcom_booking_timezone),
            "source": "mock",
            "range": {"start": start, "end": end},
        }

    tz = arguments.get("timezone", settings.calcom_booking_timezone)
    params = {
        "eventTypeId": settings.calcom_event_type_id,
        "start": arguments["start_date"],
        "end": arguments["end_date"],
        "timeZone": tz,
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            "https://api.cal.com/v2/slots",
            params=params,
            headers={
                "Authorization": f"Bearer {settings.calcom_api_key}",
                "cal-api-version": "2024-09-04",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"slots": data.get("data", data), "timezone": tz, "source": "cal.com"}
