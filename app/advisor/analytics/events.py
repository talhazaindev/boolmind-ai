"""PostHog analytics — no PII (session IDs only)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_posthog = None


def _client():
    global _posthog
    if _posthog is not None:
        return _posthog
    if not settings.posthog_configured:
        return None
    try:
        import posthog

        posthog.api_key = settings.posthog_api_key
        posthog.host = settings.posthog_host
        _posthog = posthog
        return posthog
    except ImportError:
        logger.debug("posthog package not installed")
        return None


def capture(
    event: str,
    distinct_id: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Emit server-side event; distinct_id must be session/visitor id, not email."""
    client = _client()
    if client is None:
        logger.debug("analytics %s %s", event, properties)
        return
    try:
        client.capture(distinct_id=distinct_id, event=event, properties=properties or {})
    except Exception as e:
        logger.warning("PostHog capture failed: %s", e)


def session_start(session_id: str, product: str | None = None) -> None:
    capture("session_start", session_id, {"product": product})


def message_sent(session_id: str, role: str, product: str | None = None) -> None:
    capture("message", session_id, {"role": role, "product": product})


def lead_captured(session_id: str, products: list[str]) -> None:
    capture("lead_captured", session_id, {"products_discussed": products})


def product_discussed(session_id: str, product_id: str) -> None:
    capture("product_discussed", session_id, {"product_id": product_id})


def architecture_activated(session_id: str) -> None:
    capture("architecture_activated", session_id, {})


def fidp_generated(session_id: str, product: str) -> None:
    capture("fidp_generated", session_id, {"product": product})


def discovery_evaluated(session_id: str, stage: str, missing_field_count: int) -> None:
    capture(
        "discovery_evaluated",
        session_id,
        {"stage": stage, "missing_field_count": missing_field_count},
    )


def capture_telemetry(
    session_id: str,
    event_type: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Emit advisor telemetry event to PostHog (no PII)."""
    capture(event_type, session_id, properties)
