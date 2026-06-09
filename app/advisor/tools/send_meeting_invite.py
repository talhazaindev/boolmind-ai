"""Resend meeting invite email."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.advisor.integrations.failed_operations import queue_failed_operation
from app.core.config import settings

logger = logging.getLogger(__name__)


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    if not settings.resend_configured:
        return {
            "status": "skipped",
            "message": "Invite email queued; Resend not configured.",
        }

    html = (
        f"<p>Hi {arguments['name']},</p>"
        f"<p>Your Boolmind discovery call is confirmed for {arguments['start']}.</p>"
        f"<p>Product focus: {arguments.get('product_name', 'Boolmind products')}</p>"
        f"<p>— Boolmind.AI Advisor</p>"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": f"{settings.resend_from_name} <{settings.resend_from_email}>",
                    "to": [arguments["email"]],
                    "subject": "Your Boolmind discovery call",
                    "html": html,
                },
            )
            resp.raise_for_status()
        return {"status": "sent", "email": arguments["email"]}
    except Exception as e:
        logger.exception("Resend failed: %s", e)
        await queue_failed_operation("send_meeting_invite", arguments, str(e))
        return {"status": "fallback", "message": "Booking saved; invite email will follow."}
