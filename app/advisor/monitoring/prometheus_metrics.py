"""Prometheus metrics for advisor tool and turn observability."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

TOOL_CALLS = Counter(
    "advisor_tool_calls_total",
    "Total advisor tool invocations",
    ["tool", "outcome"],
)

TOOL_DURATION = Histogram(
    "advisor_tool_duration_seconds",
    "Advisor tool execution duration",
    ["tool"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 30.0, 60.0, 180.0),
)

TURN_DURATION = Histogram(
    "advisor_turn_duration_seconds",
    "Full advisor chat turn duration",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0, 120.0),
)

FAILED_OPS_PENDING = Gauge(
    "advisor_failed_operations_pending",
    "Pending failed operations in memory queue",
)

LLM_RATE_LIMITS = Counter(
    "advisor_llm_rate_limits_total",
    "Groq rate limit events",
)


def record_tool_call(tool: str, outcome: str, duration_ms: float) -> None:
    TOOL_CALLS.labels(tool=tool, outcome=outcome).inc()
    if outcome == "success" and duration_ms > 0:
        TOOL_DURATION.labels(tool=tool).observe(duration_ms / 1000.0)


def record_turn_duration(total_ms: float) -> None:
    if total_ms > 0:
        TURN_DURATION.observe(total_ms / 1000.0)


def set_failed_ops_pending(count: int) -> None:
    FAILED_OPS_PENDING.set(count)


def record_rate_limit() -> None:
    LLM_RATE_LIMITS.inc()


def metrics_payload() -> bytes:
    return generate_latest()
