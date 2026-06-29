"""Proactive engagement rules returned from chat-init (spec 9.2.2)."""

from __future__ import annotations

from typing import Any

from app.advisor.types import PageContext


def get_proactive_triggers(
    page: PageContext,
    is_returning: bool,
) -> list[dict[str, Any]]:
    """Build client-side proactive trigger definitions."""
    url = (page.url or "").lower()
    triggers: list[dict[str, Any]] = []

    if page.product_id:
        triggers.append(
            {
                "id": "product_scroll_offer",
                "type": "scroll_depth",
                "threshold": 0.55,
                "once": True,
                "message": "Want a quick walkthrough of this product?",
                "action": "suggest_tour",
                "productId": page.product_id,
            }
        )

    if "/compare" in url:
        triggers.append(
            {
                "id": "compare_dwell",
                "type": "dwell_seconds",
                "seconds": 12,
                "once": True,
                "message": (
                    "I can compare our catalog products including Retify, ECG, Legal, "
                    "and Forecasting Engine — what matters most for your use case?"
                ),
                "action": "suggest_compare",
            }
        )

    if "/pricing" in url:
        triggers.append(
            {
                "id": "pricing_dwell",
                "type": "dwell_seconds",
                "seconds": 8,
                "once": True,
                "message": (
                    "I can't quote pricing here, but I can explain which product "
                    "fits your needs and connect you with our team."
                ),
                "action": "open_chat",
            }
        )

    triggers.append(
        {
            "id": "exit_intent",
            "type": "exit_intent",
            "once": True,
            "message": "Before you go — any last questions about our data products?",
            "action": "open_chat",
        }
    )

    if is_returning:
        triggers.append(
            {
                "id": "idle_return",
                "type": "idle_seconds",
                "seconds": 45,
                "once": True,
                "message": "Still here? Pick up where we left off or ask something new.",
                "action": "open_chat",
            }
        )

    return triggers
