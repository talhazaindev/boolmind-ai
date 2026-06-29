"""Scale context — when volume probing is satisfied or unnecessary."""

from __future__ import annotations

import re

from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

_ARR_RE = re.compile(r"\$\s*(\d[\d,]*)\s*(?:m|million|k|b|bn|billion)?\s*arr\b", re.I)
_REVENUE_RE = re.compile(
    r"(?:\$?\s*\d[\d,]*\s*(?:m|million|k|b)?\s*)?(?:arr|annual revenue|revenue)",
    re.I,
)
_LOCATIONS_RE = re.compile(
    r"(\d[\d,]*)\s*(?:clinics?|locations?|branches?|sites?|stores?|offices?)",
    re.I,
)
_GROWTH_RATE_RE = re.compile(r"\d+\s*%\s*(?:yoy|year-over-year|growth)", re.I)
_EMPLOYEES_RE = re.compile(r"(\d[\d,]*)\s*(?:\+?\s*)?(?:employees|staff|people)", re.I)

_VOLUME_PROBE_RE = re.compile(
    r"(?:roughly\s+)?what\s+volume|how\s+many\s+per\s+(?:day|week)|"
    r"volume\s+are\s+you\s+handling|how\s+much\s+volume|"
    r"how\s+big\s+is\s+(?:the\s+)?pipeline",
    re.I,
)

_THROUGHPUT_HYPOTHESES = frozenset(
    {"queue_saturation", "capacity_ceiling", "manual_handoff"}
)


def extract_business_scale_phrases(text: str) -> list[str]:
    """Non-throughput scale signals (ARR, locations, headcount)."""
    found: list[str] = []
    for pat in (_ARR_RE, _LOCATIONS_RE, _GROWTH_RATE_RE, _EMPLOYEES_RE):
        for m in pat.finditer(text):
            found.append(m.group(0).strip())
    if _REVENUE_RE.search(text) and "$" in text:
        m = re.search(r"\$\s*\d[\d,]*\s*(?:m|million|k|b)?", text, re.I)
        if m:
            found.append(m.group(0).strip())
    return list(dict.fromkeys(found))


def conversation_blob(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.data_context or "",
        message,
        " ".join(history or []),
        " ".join(snapshot.confirmed_facts),
        " ".join(snapshot.scale_indicators),
    ]
    if graph:
        parts.extend(graph.pain_points)
        for key, metric in graph.metrics.items():
            parts.append(f"{key}={metric.value}")
    return " ".join(parts)


def scale_is_satisfied(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> bool:
    """True when scale is known or contextually sufficient without daily volume."""
    if snapshot.scale_indicators or meta.data_context:
        return True
    blob = conversation_blob(meta, snapshot, message=message, history=history, graph=graph)
    if extract_business_scale_phrases(blob):
        return True
    if re.search(r"\d[\d,]*\s*(?:per day|daily|/day|per week)", blob, re.I):
        return True
    if "scale" in snapshot.resolved_unknowns:
        return True
    return False


def scale_required_for_diagnosis(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    graph: ConversationContextGraph | None = None,
) -> bool:
    """Daily/weekly throughput volume needed only for queue-capacity hypotheses."""
    if graph and graph.metrics.get("daily_volume"):
        return False
    top_ids: set[str] = set()
    if graph and hasattr(graph, "derived_inferences"):
        pass
    for hid, conf in snapshot.confidence_scores.items():
        if conf >= 0.55 and hid in _THROUGHPUT_HYPOTHESES:
            top_ids.add(hid)
    if snapshot.primary_bottleneck in ("throughput", "planning", "dispatch"):
        return True
    return bool(top_ids) and snapshot.active_business_vertical in (
        "logistics",
        "manufacturing",
    )


def is_volume_probe_question(question: str) -> bool:
    return bool(_VOLUME_PROBE_RE.search(question.lower()))
