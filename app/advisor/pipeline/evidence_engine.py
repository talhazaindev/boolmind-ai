"""Deterministic evidence accumulation across conversation turns."""

from __future__ import annotations

import re

from app.advisor.types import HypothesisSnapshot, SessionMetadata

_DRIVER_WAIT_PATTERN = re.compile(r"(\d+)\s*[-–]?\s*(\d+)?\s*minutes?", re.I)
_PROCESS_SIGNALS = (
    "spreadsheet",
    "manual planning",
    "manual dispatch",
    "coordinator",
    "excel",
    "planning is manual",
    "manual review",
    "compliance team",
    "underwriting",
    "manually gather",
)
_IMPACT_SIGNALS = (
    "driver wait",
    "drivers wait",
    "delay",
    "delays",
    "minutes",
    "backlog",
    "bottleneck",
)

# Weights sum to 0.90; base engagement floor brings turn-1 logistics to ~0.25.
_DIMENSION_WEIGHTS: dict[str, float] = {
    "industry": 0.15,
    "scale": 0.18,
    "process": 0.17,
    "pain": 0.18,
    "impact": 0.22,
}
_ENGAGEMENT_BASE = 0.10


def _conversation_blob(
    meta: SessionMetadata,
    message: str,
    history: list[str],
    snapshot: HypothesisSnapshot,
) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        meta.data_context or "",
        message,
        " ".join(history),
        " ".join(snapshot.confirmed_facts),
        " ".join(snapshot.scale_indicators),
        " ".join(snapshot.system_context),
    ]
    return " ".join(parts).lower()


def _has_industry(meta: SessionMetadata, snapshot: HypothesisSnapshot, blob: str) -> bool:
    return bool(
        snapshot.active_business_vertical
        or meta.industry
        or meta.business_type
        or snapshot.business_model != "unknown"
        or any(v in blob for v in ("logistics", "manufacturing", "retail", "saas"))
    )


def _has_scale(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    resolved: list[str],
) -> bool:
    return bool(snapshot.scale_indicators or meta.data_context or "scale" in resolved)


def _has_process(snapshot: HypothesisSnapshot, blob: str) -> bool:
    if snapshot.system_context:
        return True
    return any(sig in blob for sig in _PROCESS_SIGNALS)


def _has_pain(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    resolved: list[str],
) -> bool:
    return bool(
        meta.pain_point
        or snapshot.primary_bottleneck
        or "bottleneck" in resolved
        or "planning_delay" in resolved
    )


def _has_impact(blob: str) -> bool:
    if _DRIVER_WAIT_PATTERN.search(blob) and ("driver" in blob or "wait" in blob):
        return True
    return any(sig in blob for sig in _IMPACT_SIGNALS)


def compute_evidence_score(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    message: str,
    history: list[str],
    *,
    resolved: list[str],
) -> float:
    """Return 0.0–0.95 score from accumulated qualification dimensions."""
    blob = _conversation_blob(meta, message, history, snapshot)
    score = _ENGAGEMENT_BASE if blob.strip() else 0.0

    if _has_industry(meta, snapshot, blob):
        score += _DIMENSION_WEIGHTS["industry"]
    if _has_scale(meta, snapshot, resolved):
        score += _DIMENSION_WEIGHTS["scale"]
    if _has_process(snapshot, blob):
        score += _DIMENSION_WEIGHTS["process"]
    if _has_pain(meta, snapshot, resolved):
        score += _DIMENSION_WEIGHTS["pain"]
    if _has_impact(blob):
        score += _DIMENSION_WEIGHTS["impact"]

    return min(0.95, round(score, 2))


def merge_evidence_peak(previous_peak: float, turn_score: float) -> float:
    """Evidence only accumulates — never regress on non-informative turns."""
    return max(previous_peak, turn_score)
