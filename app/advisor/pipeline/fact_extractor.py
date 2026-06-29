"""L2 — read-only fact extraction from user message."""

from __future__ import annotations

import re

from app.advisor.orchestrator.signals.v1 import _VERTICAL_SIGNALS
from app.advisor.pipeline.types import ExtractedFacts
from app.advisor.pipeline.volume_patterns import extract_volume_indicators

_EMPLOYEE_RE = re.compile(
    r"(\d[\d,]*)\s*(employees|staff|people|workers)",
    re.I,
)
_SCALE_RE = re.compile(
    r"(\d[\d,]*)\s*"
    r"(?:loan\s+applications?|applications?|shipments|orders|transactions|loans|cases)",
    re.I,
)
_SYSTEM_KEYWORDS = ("sap", "salesforce", "hubspot", "erp", "netsuite", "dynamics")


def _vertical_from_message(message: str) -> str | None:
    lower = message.lower()
    for vertical, signals in _VERTICAL_SIGNALS.items():
        if any(sig in lower for sig in signals):
            return vertical
    return None


def extract_message_facts(message: str, history: list[str]) -> ExtractedFacts:
    """Extract proposed facts without mutating session metadata."""
    lower = message.lower()
    vertical = _vertical_from_message(message)
    if re.search(r"\b(logistics|dispatch|fleet|shipment)\b", message, re.I):
        vertical = "logistics"
    elif re.search(r"\b(manufacturing)\b", message, re.I):
        vertical = "manufacturing"
    elif re.search(r"\b(lending|loan|underwriting|origination)\b", message, re.I):
        vertical = "financial_services"

    scale: str | None = None
    m = _SCALE_RE.search(message)
    if m:
        scale = m.group(0).strip()
    else:
        volumes = extract_volume_indicators(message)
        if volumes:
            scale = volumes[0]

    employee_count: int | None = None
    em = _EMPLOYEE_RE.search(message)
    if em:
        employee_count = int(em.group(1).replace(",", ""))

    systems = [kw for kw in _SYSTEM_KEYWORDS if kw in lower]

    return ExtractedFacts(
        proposed_vertical=vertical,
        proposed_industry=vertical,
        proposed_scale=scale,
        proposed_employee_count=employee_count,
        proposed_systems=systems,
        claims_fully_automated=any(
            p in lower for p in ("fully automated", "completely automated", "100% automated")
        ),
        claims_manual_process=any(
            p in lower for p in ("manual", "spreadsheet", "by hand")
        ),
    )
