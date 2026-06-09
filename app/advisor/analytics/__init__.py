"""Advisor analytics."""

from app.advisor.analytics.events import (
    architecture_activated,
    capture,
    fidp_generated,
    lead_captured,
    message_sent,
    product_discussed,
    session_start,
)

__all__ = [
    "capture",
    "session_start",
    "message_sent",
    "lead_captured",
    "product_discussed",
    "architecture_activated",
    "fidp_generated",
]
