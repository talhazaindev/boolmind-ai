"""In-process metrics rollup for admin dashboard (last 1h window)."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_WINDOW_SECONDS = 3600


@dataclass
class _RollupEntry:
    timestamp: float
    event_type: str
    metadata: dict[str, Any]


_rollup_buffer: list[_RollupEntry] = []


def record_rollup(event_type: str, metadata: dict[str, Any] | None) -> None:
    _rollup_buffer.append(
        _RollupEntry(
            timestamp=time.time(),
            event_type=event_type,
            metadata=metadata or {},
        )
    )
    cutoff = time.time() - _WINDOW_SECONDS
    while _rollup_buffer and _rollup_buffer[0].timestamp < cutoff:
        _rollup_buffer.pop(0)


def metrics_summary() -> dict[str, Any]:
    cutoff = time.time() - _WINDOW_SECONDS
    recent = [e for e in _rollup_buffer if e.timestamp >= cutoff]

    tool_outcomes: dict[str, int] = defaultdict(int)
    tool_latencies: list[float] = []
    rate_limits = 0
    evaluator_fallbacks = 0
    failed_ops_queued = 0
    turns = 0
    turn_latencies: list[float] = []

    for entry in recent:
        if entry.event_type == "tool_completed":
            tool_outcomes["success"] += 1
            if "duration_ms" in entry.metadata:
                tool_latencies.append(float(entry.metadata["duration_ms"]))
        elif entry.event_type == "tool_timeout":
            tool_outcomes["timeout"] += 1
        elif entry.event_type == "tool_failed":
            tool_outcomes["error"] += 1
        elif entry.event_type == "tool_gated":
            tool_outcomes["gated"] += 1
        elif entry.event_type == "llm_rate_limited":
            rate_limits += 1
        elif entry.event_type == "evaluator_fallback":
            evaluator_fallbacks += 1
        elif entry.event_type == "failed_operation_queued":
            failed_ops_queued += 1
        elif entry.event_type == "turn_completed":
            turns += 1
            total = entry.metadata.get("total_ms")
            if total is not None:
                turn_latencies.append(float(total))

    avg_tool_ms = (
        round(sum(tool_latencies) / len(tool_latencies), 1) if tool_latencies else 0.0
    )
    p95_tool_ms = 0.0
    if tool_latencies:
        sorted_lat = sorted(tool_latencies)
        idx = int(len(sorted_lat) * 0.95) - 1
        p95_tool_ms = round(sorted_lat[max(0, idx)], 1)

    return {
        "window_seconds": _WINDOW_SECONDS,
        "tool_outcomes": dict(tool_outcomes),
        "avg_tool_latency_ms": avg_tool_ms,
        "p95_tool_latency_ms": p95_tool_ms,
        "rate_limit_count": rate_limits,
        "evaluator_fallback_count": evaluator_fallbacks,
        "failed_ops_queued_count": failed_ops_queued,
        "turn_count": turns,
        "avg_turn_latency_ms": (
            round(sum(turn_latencies) / len(turn_latencies), 1) if turn_latencies else 0.0
        ),
    }


def clear_rollup() -> None:
    """Clear rollup buffer (tests only)."""
    _rollup_buffer.clear()
