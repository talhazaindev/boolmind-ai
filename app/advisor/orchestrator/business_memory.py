"""Scored business memory with confidence and expiry."""

from __future__ import annotations

import re

from app.advisor.orchestrator.signals import get_signal_registry
from app.advisor.orchestrator.signals.v1 import _VERTICAL_SIGNALS
from app.advisor.pipeline.volume_patterns import extract_backlog_count, extract_volume_indicators
from app.advisor.types import (
    BusinessMemorySnapshot,
    HypothesisSnapshot,
    ProductFitDecision,
    ScoredMemoryLine,
    SessionMetadata,
)

MEMORY_EXPIRE_CONFIDENCE = 0.5
MEMORY_EXPIRE_TURNS = 3
MEMORY_IMMEDIATE_EXPIRE = 0.3
PROMPT_MIN_CONFIDENCE = 0.5

_SCALE_RE = re.compile(
    r"(\d[\d,]*)\s*"
    r"(?:loan\s+applications?|applications?|shipments|orders|loans|cases|transactions)",
    re.I,
)
_COORDINATOR_RE = re.compile(r"(\d+)\s*coordinators?", re.I)
_DRIVER_WAIT_RE = re.compile(r"(\d+)\s*[-–]?\s*(\d+)?\s*minutes?", re.I)


def _find_line(lines: list[ScoredMemoryLine], key: str) -> ScoredMemoryLine | None:
    for line in lines:
        if line.key == key:
            return line
    return None


def _vertical_from_message(message: str) -> str | None:
    lower = message.lower()
    for vertical, signals in _VERTICAL_SIGNALS.items():
        if any(sig in lower for sig in signals):
            return vertical
    return None


def _message_fact_candidates(message: str) -> list[tuple[str, str, float]]:
    """Extract high-value facts directly from user message."""
    candidates: list[tuple[str, str, float]] = []
    lower = message.lower()

    vertical = _vertical_from_message(message)
    if vertical:
        conf = 1.0 if re.search(r"we (are|run|operate)", message, re.I) else 0.92
        candidates.append(("business_vertical", vertical, conf))
        candidates.append(("industry", vertical, conf))

    m = _SCALE_RE.search(message)
    if m:
        candidates.append(("scale", m.group(0).strip(), 0.95))
    for vol in extract_volume_indicators(message):
        if not any(c[0] == "scale" for c in candidates):
            candidates.append(("scale", vol, 0.95))

    backlog = extract_backlog_count(message)
    if backlog:
        candidates.append(("backlog_size", backlog, 0.92))

    if "compliance" in lower and "manual" in lower:
        candidates.append(("compliance_process", "manual compliance reviews", 0.9))

    if any(p in lower for p in ("automation", "automated")) and any(
        p in lower for p in ("fail", "poor adoption", "exception", "revert", "went back")
    ):
        candidates.append(("automation_history", "prior automation failed", 0.88))

    cm = _COORDINATOR_RE.search(message)
    if cm:
        candidates.append(("planning_team", f"{cm.group(1)} coordinators", 0.9))

    if "spreadsheet" in lower:
        candidates.append(("planning_tool", "spreadsheets", 0.95))

    if "driver" in lower and ("wait" in lower or "minute" in lower):
        dw = _DRIVER_WAIT_RE.search(message)
        val = dw.group(0) if dw else "30-60 minutes"
        candidates.append(("driver_wait", val, 0.95))

    if "manual" in lower and ("plan" in lower or "dispatch" in lower):
        candidates.append(("planning_method", "manual planning", 0.9))

    return candidates


def _candidate_lines(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    fit: ProductFitDecision,
    message: str,
    turn: int,
) -> list[tuple[str, str, float]]:
    candidates: list[tuple[str, str, float]] = []
    candidates.extend(_message_fact_candidates(message))

    if meta.industry and not any(c[0] == "industry" for c in candidates):
        conf = 1.0 if re.search(r"we (are|operate)", message, re.I) else 0.9
        candidates.append(("industry", meta.industry, conf))
    if snapshot.active_business_vertical:
        candidates.append((
            "business_vertical",
            snapshot.active_business_vertical,
            0.92,
        ))
    if snapshot.primary_bottleneck:
        candidates.append(("primary_bottleneck", snapshot.primary_bottleneck, 0.85))
    if meta.goals:
        candidates.append(("goal", meta.goals[:80], 0.85))
    for ctx in snapshot.system_context:
        candidates.append((f"system_{ctx}", ctx, 0.9))
    for scale in snapshot.scale_indicators[:2]:
        if not any(c[0] == "scale" for c in candidates):
            candidates.append(("scale", scale, 0.9))
    for fact in snapshot.confirmed_facts[:6]:
        candidates.append((f"fact_{fact[:20]}", fact, 0.88))
    if fit.catalog_product_fit:
        candidates.append(("catalog_product_fit", fit.catalog_product_fit, fit.confidence))
    if fit.solution_category:
        candidates.append(("solution_category", fit.solution_category, fit.confidence))

    signals = get_signal_registry()
    for pat in signals.explicit_statement_patterns:
        if re.search(pat, message, re.I):
            for key, value, conf in list(candidates):
                if key == "business_vertical":
                    candidates.append((key, value, 1.0))

    return candidates


def update_business_memory(
    existing_lines: list[ScoredMemoryLine],
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    fit: ProductFitDecision,
    message: str,
    turn: int,
) -> tuple[list[ScoredMemoryLine], BusinessMemorySnapshot]:
    lines = [line.model_copy() for line in existing_lines]
    candidates = _candidate_lines(meta, snapshot, fit, message, turn)

    for key, value, conf in candidates:
        existing = _find_line(lines, key)
        if existing:
            if existing.value.lower() != value.lower():
                existing.contradict_count += 1
                existing.confidence = max(0.0, existing.confidence - 0.25)
            else:
                existing.last_confirmed_turn = turn
                existing.confidence = min(1.0, existing.confidence + 0.05)
        else:
            lines.append(
                ScoredMemoryLine(
                    key=key,
                    value=value,
                    confidence=conf,
                    source_turn=turn,
                    last_confirmed_turn=turn,
                )
            )

    kept: list[ScoredMemoryLine] = []
    for line in lines:
        turns_since = turn - line.last_confirmed_turn
        if line.confidence < MEMORY_IMMEDIATE_EXPIRE:
            continue
        if line.confidence < MEMORY_EXPIRE_CONFIDENCE and turns_since >= MEMORY_EXPIRE_TURNS:
            continue
        kept.append(line)

    snapshot_lines = tuple(
        line for line in kept if line.confidence >= PROMPT_MIN_CONFIDENCE
    )
    return kept, BusinessMemorySnapshot(version="v1", lines=snapshot_lines)


def render_known_facts_block(snapshot: HypothesisSnapshot) -> str:
    if not snapshot.confirmed_facts:
        return ""
    rows = "\n".join(f"- {fact}" for fact in snapshot.confirmed_facts)
    return (
        "KNOWN FACTS (do not ask questions contradicted by these):\n"
        f"{rows}"
    )


def render_business_memory_block(
    memory: BusinessMemorySnapshot,
    snapshot: HypothesisSnapshot | None = None,
    context_graph: object | None = None,
) -> str:
    parts: list[str] = []
    if snapshot:
        known = render_known_facts_block(snapshot)
        if known:
            parts.append(known)
    if context_graph is not None and hasattr(context_graph, "metrics"):
        metrics = getattr(context_graph, "metrics", {})
        if metrics:
            rows = [
                f"{key}={getattr(val, 'value', val)}"
                for key, val in metrics.items()
            ]
            parts.append(
                "CONVERSATION_STATE (never ask about populated fields):\n"
                + "\n".join(rows)
            )
    if memory.lines:
        rows = [f"{line.key}={line.value} ({line.confidence:.2f})" for line in memory.lines]
        parts.append("BUSINESS_MEMORY:\n" + "\n".join(rows))
    return "\n\n".join(parts)


def memory_consistency_violations(
    question: str | None,
    snapshot: HypothesisSnapshot,
) -> list[str]:
    """Return list of violations if question contradicts known facts."""
    if not question:
        return []
    q = question.lower()
    violations: list[str] = []
    facts_blob = " ".join(snapshot.confirmed_facts).lower()

    if "which step creates the most delay" in q:
        if "planning" in facts_blob or "planning_delay" in snapshot.resolved_unknowns:
            violations.append("bottleneck_already_implied_planning")
    if "logistics or manufacturing" in q or "separate business" not in q:
        if snapshot.active_business_vertical and "manufacturing" not in facts_blob:
            if "logistics" in facts_blob and "manufacturing" in q:
                pass  # ok if clarifying
    return violations
