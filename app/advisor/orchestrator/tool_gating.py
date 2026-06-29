"""Tool readiness gating for discovery funnel (Phase 7)."""

from __future__ import annotations

from typing import Any

from app.advisor.constants import (
    ALWAYS_AVAILABLE_TOOLS,
    PRODUCT_FIT_CONFIDENCE_MIN,
    TOOL_READINESS_KEY,
)
from app.advisor.types import ConversationStage, ReadinessFlags, SessionMetadata

_STAGE_ORDER: dict[ConversationStage, int] = {
    "EXPLORE": 0,
    "INTEREST": 1,
    "QUALIFY": 2,
    "CAPTURE": 3,
    "BOOK": 4,
    "DONE": 5,
}

STAGE_ORDER = _STAGE_ORDER

_DEFERRED_TOOL_PATTERNS: dict[str, list[str]] = {
    "product_tour": [r"\btour\b", r"\bwalkthrough\b", r"\bdemo\b", r"\bshow me how\b"],
    "generate_architecture_proposal": [
        r"\barchitecture\b",
        r"\bdesign\s+(a|the)\s+system\b",
        r"\btechnical\s+solution\b",
    ],
    "generate_fidp": [r"\bvisual\s+preview\b", r"\bmockup\b", r"\binterface\s+preview\b"],
    "calendar_get_slots": [r"\bbook\b", r"\bschedule\b", r"\bcalendar\b", r"\bdemo call\b"],
}


def has_business_context(meta: SessionMetadata) -> bool:
    return bool(meta.business_type or meta.industry)


def has_minimum_discovery_context(meta: SessionMetadata) -> bool:
    return (
        has_business_context(meta)
        and bool(meta.pain_point)
        and bool(meta.goals)
    )


def compute_rule_based_readiness(meta: SessionMetadata) -> ReadinessFlags:
    """Code-enforced readiness gates on top of LLM evaluation."""
    minimum = has_minimum_discovery_context(meta)
    stage = meta.stage_reached
    stage_idx = _STAGE_ORDER.get(stage, 0)

    product_fit_ok = (
        meta.product_fit is not None
        and meta.product_fit != "undecided"
        and meta.product_fit_confidence >= PRODUCT_FIT_CONFIDENCE_MIN
    )
    has_data_context = bool(meta.data_context)
    has_contact = bool(meta.visitor_name and meta.collected_email)

    tour_allowed = (
        minimum
        and product_fit_ok
        and stage_idx >= _STAGE_ORDER["INTEREST"]
        and meta.product_fit != "custom_solutions"
    )
    return ReadinessFlags(
        architecture=minimum and has_data_context and stage_idx >= _STAGE_ORDER["QUALIFY"],
        product_tour=tour_allowed,
        fidp=minimum and has_data_context and stage_idx >= _STAGE_ORDER["QUALIFY"],
        lead_capture=minimum and stage_idx >= _STAGE_ORDER["CAPTURE"],
        booking=minimum and has_contact and stage_idx >= _STAGE_ORDER["CAPTURE"],
    )


def effective_readiness(
    meta: SessionMetadata,
    llm_readiness: ReadinessFlags,
) -> ReadinessFlags:
    """Intersection of LLM readiness and rule-based gates."""
    rules = compute_rule_based_readiness(meta)
    return ReadinessFlags(
        architecture=llm_readiness.architecture and rules.architecture,
        product_tour=llm_readiness.product_tour and rules.product_tour,
        fidp=llm_readiness.fidp and rules.fidp,
        lead_capture=llm_readiness.lead_capture and rules.lead_capture,
        booking=llm_readiness.booking and rules.booking,
    )


def is_tool_allowed(
    tool_name: str,
    readiness: ReadinessFlags,
    product_fit: str | None = None,
) -> bool:
    if tool_name == "product_tour" and product_fit == "custom_solutions":
        return False
    if tool_name in ALWAYS_AVAILABLE_TOOLS:
        return True
    readiness_key = TOOL_READINESS_KEY.get(tool_name)
    if readiness_key is None:
        return True
    return bool(getattr(readiness, readiness_key, False))


def filter_tool_definitions(
    tools: list[dict[str, Any]],
    readiness: ReadinessFlags,
    product_fit: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for tool in tools:
        name = tool.get("function", {}).get("name", "")
        if is_tool_allowed(name, readiness, product_fit=product_fit):
            filtered.append(tool)
    return filtered


def gated_tool_fallback(tool_name: str) -> str:
    return (
        f"The {tool_name.replace('_', ' ')} deliverable is not ready yet — "
        "continue discovery with the user first."
    )


def detect_deferred_deliverable_request(message: str) -> str | None:
    import re

    lower = message.lower()
    for tool_name, patterns in _DEFERRED_TOOL_PATTERNS.items():
        if any(re.search(pat, lower) for pat in patterns):
            if tool_name in TOOL_READINESS_KEY:
                return tool_name
    return None
