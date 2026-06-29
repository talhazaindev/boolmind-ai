"""Deterministic derived metrics from conversation context."""

from __future__ import annotations

import re

from app.advisor.types import ConversationContextGraph, MetricValue


def _metric_number(metrics: dict[str, MetricValue], key: str) -> float | None:
    raw = metrics.get(key)
    if raw is None:
        return None
    if isinstance(raw.value, (int, float)):
        return float(raw.value)
    if isinstance(raw.value, str):
        m = re.search(r"[\d,]+", raw.value.replace(",", ""))
        if m:
            return float(m.group(0))
    return None


def build_derived_inferences(graph: ConversationContextGraph) -> list[str]:
    """Compute queue depth, delay delta, and similar operational inferences."""
    inferences: list[str] = []
    daily = _metric_number(graph.metrics, "daily_volume")
    backlog = _metric_number(graph.metrics, "backlog")
    current = _metric_number(graph.metrics, "turnaround_days_current")
    baseline = _metric_number(graph.metrics, "turnaround_days_baseline")

    if daily and daily > 0 and backlog and backlog > 0:
        queue_days = round(backlog / daily, 1)
        inferences.append(
            f"A backlog of {int(backlog)} at {int(daily)}/day is roughly "
            f"{queue_days} days of volume sitting in queue."
        )
        graph.metrics["queue_days"] = MetricValue(
            value=queue_days, unit="days", source="derived", confidence=0.85
        )

    if current is not None and baseline is not None and current > baseline:
        delta = round(current - baseline, 1)
        inferences.append(
            f"Turnaround slipped from {int(baseline)} to {int(current)} days "
            f"— about {delta} days of new delay to explain."
        )
        graph.metrics["turnaround_delay_delta"] = MetricValue(
            value=delta, unit="days", source="derived", confidence=0.85
        )

    graph.derived_inferences = list(dict.fromkeys(inferences))
    return graph.derived_inferences


def acknowledgment_snippets(graph: ConversationContextGraph) -> list[str]:
    """Short phrases the narrator LLM should weave into acknowledgment."""
    snippets: list[str] = []
    snippets.extend(graph.derived_inferences[:2])
    if graph.pain_points:
        snippets.append(f"Pain point: {graph.pain_points[0]}")
    if graph.prior_attempts:
        attempt = graph.prior_attempts[0]
        snippets.append(f"Prior attempt: {attempt.what} ({attempt.outcome})")
    return snippets[:3]
