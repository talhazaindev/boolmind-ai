"""Detect contradictions between active hypothesis and new user facts."""

from __future__ import annotations

import re

from app.advisor.orchestrator.signals.v1 import _VERTICAL_SIGNALS
from app.advisor.types import ScoredMemoryLine, SessionMetadata


def _verticals_in_text(text: str) -> set[str]:
    lower = text.lower()
    found: set[str] = set()
    for vertical, signals in _VERTICAL_SIGNALS.items():
        if any(sig in lower for sig in signals):
            found.add(vertical)
    return found


def _memory_vertical(lines: list[ScoredMemoryLine]) -> str | None:
    for line in lines:
        if line.key == "business_vertical" and line.confidence >= 0.5:
            return line.value
        if line.key == "industry" and line.confidence >= 0.5:
            return line.value
    return None


def detect_hypothesis_conflict(
    message: str,
    history: list[str],
    meta: SessionMetadata,
    memory_lines: list[ScoredMemoryLine],
) -> tuple[bool, str | None]:
    """
    Return (is_conflicted, clarification_prompt_fragment).
    Compares new message verticals against established business memory.
    """
    prior_vertical = meta.active_business_vertical or _memory_vertical(memory_lines)
    if not prior_vertical:
        return False, None

    new_verticals = _verticals_in_text(message)
    if not new_verticals:
        return False, None

    # Direct vertical switch (logistics → manufacturing)
    if prior_vertical in new_verticals:
        return False, None

    conflicting = new_verticals - {prior_vertical}
    if not conflicting:
        return False, None

    new_v = next(iter(conflicting))
    prior_facts = _summarize_prior_facts(memory_lines, meta)
    return True, (
        f"Earlier you described a {prior_vertical} operation ({prior_facts}). "
        f"Now you've mentioned being a {new_v} business. "
        f"Are these separate business units, or should I update my understanding?"
    )


def _summarize_prior_facts(
    lines: list[ScoredMemoryLine],
    meta: SessionMetadata,
) -> str:
    parts: list[str] = []
    for line in lines:
        if line.confidence >= 0.5 and line.key in (
            "scale", "planning_tool", "driver_wait", "planning_team",
        ):
            parts.append(f"{line.key}={line.value}")
    if meta.data_context:
        m = re.search(r"\d+[\d,]*\s*(shipments|orders)", meta.data_context, re.I)
        if m:
            parts.append(m.group(0))
    return ", ".join(parts[:3]) if parts else "prior context discussed"
