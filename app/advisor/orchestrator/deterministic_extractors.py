"""Rule-based meta field extraction — no LLM."""

from __future__ import annotations

import re

from app.advisor.orchestrator.signals import get_signal_registry
from app.advisor.pipeline.volume_patterns import extract_volume_indicators
from app.advisor.types import SessionMetadata

_PROPOSED_TOOL_PATTERN = re.compile(
    r"\b(?:considering|evaluating|exploring|looking at|planning to (?:buy|adopt|implement))\b",
    re.I,
)
_HEALTHCARE_SIGNALS = (
    "healthcare",
    "hospital",
    "clinic",
    "patient",
    "medical",
    "veterinary",
    "dental",
    "physician",
    "appointment",
)
_SERVICE_SIGNALS = (
    "services group",
    "service business",
    "professional services",
    "consulting firm",
    "practice",
)


def _keyword_is_proposed_tool(blob: str, keyword: str) -> bool:
    """Ignore product keywords that appear only in proposed-tool context."""
    if keyword != "software":
        return False
    for m in _PROPOSED_TOOL_PATTERN.finditer(blob):
        window = blob[m.start() : m.end() + 80]
        if keyword in window:
            return True
    return False


def deterministic_meta_extractors(
    message: str,
    history: list[str],
    meta: SessionMetadata,
) -> SessionMetadata:
    """Return meta with rule-extracted profile fields merged."""
    updated = meta.model_copy(deep=True)
    blob = " ".join([message, *history[-6:]]).lower()
    signals = get_signal_registry()

    # Prefer explicit vertical in current message over history scan
    if re.search(r"\b(logistics|dispatch|fleet|shipment)\b", message, re.I):
        updated.industry = "logistics"
        updated.active_business_vertical = "logistics"
    elif re.search(r"\bmanufacturing\b", message, re.I):
        updated.industry = "manufacturing"
        updated.active_business_vertical = "manufacturing"
    elif re.search(r"\b(lending|loan|underwriting|origination)\b", message, re.I):
        updated.industry = "financial_services"
        updated.active_business_vertical = "financial_services"
    elif not updated.industry:
        for industry in ("logistics", "retail", "healthcare", "education", "manufacturing"):
            if industry in blob:
                updated.industry = industry
                updated.active_business_vertical = industry
                break
        if not updated.industry and any(sig in blob for sig in _HEALTHCARE_SIGNALS):
            updated.industry = "healthcare"
            updated.active_business_vertical = "healthcare"

    if not updated.business_type:
        if any(sig in blob for sig in _SERVICE_SIGNALS):
            updated.business_model = "service"
            updated.business_type = "service"
        else:
            for model, keywords in signals.business_model_signals.items():
                if any(kw in blob and not _keyword_is_proposed_tool(blob, kw) for kw in keywords):
                    updated.business_model = model
                    updated.business_type = model
                    break

    if not updated.pain_point:
        pain_signals = (
            "delay", "bottleneck", "manual", "slow", "error", "backlog",
            "churn", "turnover", "margin", "cost",
        )
        for sig in pain_signals:
            if sig in blob:
                updated.pain_point = sig
                break

    if not updated.goals:
        goal_signals = ("reduce", "improve", "increase", "optimize", "scale")
        for sig in goal_signals:
            if re.search(rf"\b{sig}\b", blob):
                updated.goals = message[:120]
                break

    for pat in signals.explicit_statement_patterns:
        m = re.search(pat, message, re.I)
        if m and not updated.data_context:
            updated.data_context = m.group(0)[:80]

    if not updated.data_context:
        volumes = extract_volume_indicators(blob)
        if volumes:
            updated.data_context = volumes[0]

    updated.message_count = max(updated.message_count, meta.message_count)
    return updated
