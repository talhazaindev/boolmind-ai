"""Shared volume/scale extraction — vertical-agnostic."""

from __future__ import annotations

import re

_VOLUME_UNIT_RE = re.compile(
    r"(\d[\d,]*)\s*"
    r"(loan\s+applications?|applications?|cases?|requests?|tickets?|"
    r"transactions?|orders?|shipments?|deliveries?|loans?|"
    r"customers?|users?|units?|items?)"
    r"(?:\s*(?:per\s+day|daily|a\s+day|/day|per\s+week|weekly))?",
    re.I,
)

_SIMPLE_DAILY_VOLUME_RE = re.compile(
    r"(\d[\d,]*)\s*(?:per\s+day|daily|a\s+day|/day)",
    re.I,
)

_BACKLOG_RE = re.compile(
    r"(?:backlog\s+of\s+about\s+|backlog\s+of\s+)?(\d[\d,]*)\s*(?:applications?|loans?|cases?)?",
    re.I,
)


def extract_volume_indicators(text: str) -> list[str]:
    """Return normalized volume phrases found in *text*."""
    found: list[str] = []
    for m in _VOLUME_UNIT_RE.finditer(text):
        unit = m.group(2).lower()
        count = m.group(1).replace(",", "")
        tail = m.group(0).lower()
        if "week" in tail:
            found.append(f"{count} {unit}/week")
        elif "day" in tail or "daily" in tail:
            found.append(f"{count} {unit}/day")
        else:
            found.append(f"{count} {unit}/day")
    if not found:
        m = _SIMPLE_DAILY_VOLUME_RE.search(text)
        if m:
            found.append(f"{m.group(1)}/day")
    return list(dict.fromkeys(found))


def extract_backlog_count(text: str) -> str | None:
    """Return backlog size phrase when explicitly stated."""
    lower = text.lower()
    if "backlog" not in lower:
        return None
    m = _BACKLOG_RE.search(text)
    if m:
        suffix = " applications" if "application" in lower or "loan" in lower else ""
        return f"{m.group(1).replace(',', '')}{suffix} backlog"
    return "backlog reported"
