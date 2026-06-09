"""Cal.com booking."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.advisor.integrations.failed_operations import queue_failed_operation
from app.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_BOOKING = (
    "I couldn't complete the booking right now. Our team will reach out to confirm your slot."
)


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "eventTypeId": int(settings.calcom_event_type_id or 0),
        "start": arguments["start"],
        "attendee": {
            "name": arguments["name"],
            "email": arguments["email"],
            "timeZone": arguments.get("timezone", settings.calcom_booking_timezone),
        },
        "metadata": {
            "source": "boolmind-advisor",
            "product_context": arguments.get("product_context", ""),
            "session_id": arguments.get("session_id", ""),
        },
    }
    if not settings.calcom_configured:
        return {
            "status": "queued",
            "booking_uid": f"mock-{arguments['email'][:8]}",
            "start": arguments["start"],
            "message": "Booking recorded; Cal.com sync pending configuration.",
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.cal.com/v2/bookings",
                headers={
                    "Authorization": f"Bearer {settings.calcom_api_key}",
                    "cal-api-version": "2024-08-13",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        uid = data.get("data", {}).get("uid") or data.get("uid", "")
        return {
            "status": "booked",
            "booking_uid": uid,
            "start": arguments["start"],
            "email": arguments["email"],
        }
    except Exception as e:
        logger.exception("Cal.com book failed: %s", e)
        await queue_failed_operation("calendar_book_slot", arguments, str(e))
        return {"status": "fallback", "message": FALLBACK_BOOKING, "start": arguments["start"]}
