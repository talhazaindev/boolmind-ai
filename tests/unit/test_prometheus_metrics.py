"""Prometheus metrics tests."""

from __future__ import annotations

from app.advisor.monitoring.prometheus_metrics import (
    metrics_payload,
    record_tool_call,
    record_turn_duration,
)


def test_record_tool_call_and_metrics_export() -> None:
    record_tool_call("rag_query", "success", 150.0)
    record_turn_duration(2500.0)
    payload = metrics_payload().decode("utf-8")
    assert "advisor_tool_calls_total" in payload
    assert "advisor_turn_duration_seconds" in payload
