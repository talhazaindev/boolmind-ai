"""HubSpot CRM lead creation."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.advisor.analytics.events import lead_captured
from app.advisor.integrations.redis_store import get_redis_store
from app.core.config import settings

logger = logging.getLogger(__name__)


async def handle(
    arguments: dict[str, Any],
    session_id: str,
    visitor_id: str | None,
) -> dict[str, Any]:
    email = (arguments.get("email") or "").strip().lower()
    if visitor_id and email:
        redis = get_redis_store()
        meta = await redis.get_visitor_metadata(visitor_id)
        if meta and email in meta.crm_captured_emails:
            return {
                "status": "duplicate",
                "message": "Lead already captured for this visitor.",
                "email": email,
            }

    if not settings.hubspot_configured:
        logger.info("HubSpot not configured — lead logged locally: %s", arguments.get("email"))
        return {
            "status": "queued",
            "message": "Lead recorded; CRM sync pending configuration.",
            "email": arguments.get("email"),
        }

    name = arguments.get("name", "")
    parts = name.split(" ", 1)
    firstname = parts[0]
    lastname = parts[1] if len(parts) > 1 else ""

    products = arguments.get("products_discussed", [])
    properties = {
        "email": arguments.get("email"),
        "firstname": firstname,
        "lastname": lastname,
        "hs_lead_source": "chatbot",
        "chatbot_use_case": arguments.get("use_case", ""),
        "chatbot_products_discussed": ",".join(products) if products else "",
        "chatbot_primary_product": arguments.get("primary_product", ""),
        "chatbot_qualification_score": str(arguments.get("qualification_score", 5)),
        "chatbot_stage_at_capture": arguments.get("stage_at_capture", "CAPTURE"),
        "chatbot_session_id": session_id,
    }
    if arguments.get("company"):
        properties["company"] = arguments["company"]

    async with httpx.AsyncClient(timeout=10.0) as client:  # noqa: ASYNC100
        resp = await client.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers={
                "Authorization": f"Bearer {settings.hubspot_access_token}",
                "Content-Type": "application/json",
            },
            json={"properties": properties},
        )
        resp.raise_for_status()
        data = resp.json()

    products = arguments.get("products_discussed", [])
    lead_captured(session_id, products)
    if visitor_id and email:
        redis = get_redis_store()
        meta = await redis.get_visitor_metadata(visitor_id)
        if meta:
            emails = list(meta.crm_captured_emails)
            if email not in emails:
                emails.append(email)
            meta.crm_captured_emails = emails
            meta.collected_email = email
            meta.visitor_name = arguments.get("name") or meta.visitor_name
            await redis.save_visitor_metadata(visitor_id, meta)

    return {"status": "created", "hubspot_id": data.get("id"), "email": arguments.get("email")}
