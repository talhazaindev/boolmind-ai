"""Active conversation thread tracking for progressive deepening."""

from __future__ import annotations

from app.advisor.types import ConversationContextGraph, SessionMetadata

_THREAD_REQUIRES_ALL: frozenset[str] = frozenset({"compliance_backlog"})

_COMPLIANCE_HANDOFF_SIGNALS: tuple[str, ...] = (
    "risk team",
    "move between",
    "handoff",
    "compliance analysts",
)


def _thread_score(thread_id: str, signals: tuple[str, ...], blob: str) -> int:
    if thread_id == "compliance_handoff":
        if "compliance" in blob and any(s in blob for s in _COMPLIANCE_HANDOFF_SIGNALS):
            return 2
        return 0
    hit = sum(1 for s in signals if s in blob)
    if thread_id in _THREAD_REQUIRES_ALL and hit < len(signals):
        return 0
    return hit


_THREAD_SIGNALS: dict[str, tuple[str, ...]] = {
    "failed_doc_automation": (
        "automation",
        "exception",
        "went back to email",
        "poor adoption",
        "missed exceptions",
    ),
    "compliance_backlog": (
        "compliance",
        "backlog",
    ),
    "compliance_handoff": (
        "compliance",
        "risk team",
        "move between",
        "handoff",
    ),
    "underwriting_capacity": (
        "underwriting",
        "analyst",
        "financial statement",
        "manual gather",
    ),
    "planning_bottleneck": (
        "spreadsheet",
        "coordinator",
        "driver wait",
        "dispatch delay",
        "planning",
    ),
    "scale_growth": (
        "volume",
        "per day",
        "shipments",
        "applications per day",
    ),
}


def detect_thread(message: str, graph: ConversationContextGraph) -> str | None:
    blob = message.lower()
    if graph.prior_attempts:
        return "failed_doc_automation"
    scores: dict[str, int] = {}
    for thread_id, signals in _THREAD_SIGNALS.items():
        scores[thread_id] = _thread_score(thread_id, signals, blob)
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else None


def update_active_thread(
    meta: SessionMetadata,
    message: str,
    graph: ConversationContextGraph,
) -> ConversationContextGraph:
    """Stay on active thread for 2 turns unless user pivots."""
    detected = detect_thread(message, graph)
    current = meta.active_thread or graph.active_thread

    if detected and detected != current:
        graph.active_thread = detected
        graph.thread_depth = 1
    elif current:
        graph.active_thread = current
        graph.thread_depth = meta.active_thread_depth + 1
    elif detected:
        graph.active_thread = detected
        graph.thread_depth = 1
    else:
        graph.active_thread = current
        graph.thread_depth = meta.active_thread_depth

    if graph.thread_depth > 2 and not detected:
        graph.active_thread = detected or current
        if detected and detected != current:
            graph.thread_depth = 1

    return graph


def thread_continuation_required(graph: ConversationContextGraph) -> bool:
    return bool(graph.active_thread) and graph.thread_depth < 2
