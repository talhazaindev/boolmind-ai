"""Telemetry module tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.advisor.monitoring import events as ev
from app.advisor.monitoring.rollup import clear_rollup, metrics_summary
from app.advisor.monitoring.telemetry import emit


def test_sanitize_metadata_strips_pii() -> None:
    meta = {
        "tool": "crm_create_lead",
        "email": "user@example.com",
        "name": "Jane Doe",
        "nested": {"phone": "555-1234"},
    }
    cleaned = ev.sanitize_metadata(meta)
    assert cleaned["email"] == "[redacted]"
    assert cleaned["name"] == "[redacted]"
    assert cleaned["nested"]["phone"] == "[redacted]"
    assert cleaned["tool"] == "crm_create_lead"


@pytest.mark.asyncio
async def test_emit_never_raises_on_sink_failure() -> None:
    with patch(
        "app.advisor.monitoring.telemetry._emit_supabase",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db down"),
    ):
        await emit("tool_completed", "sess-1", metadata={"tool": "rag_query", "duration_ms": 10})


@pytest.mark.asyncio
async def test_emit_records_rollup() -> None:
    clear_rollup()
    with patch("app.advisor.monitoring.telemetry._emit_supabase", new_callable=AsyncMock):
        with patch("app.advisor.monitoring.telemetry._emit_posthog"):
            with patch("app.advisor.monitoring.telemetry._emit_prometheus"):
                with patch("app.advisor.monitoring.telemetry._emit_sentry"):
                    with patch("app.advisor.monitoring.telemetry._emit_structured_log"):
                        await emit(
                            "tool_completed",
                            "sess-1",
                            metadata={"tool": "rag_query", "duration_ms": 100, "outcome": "success"},
                        )
    summary = metrics_summary()
    assert summary["tool_outcomes"].get("success") == 1
    clear_rollup()


@pytest.mark.asyncio
async def test_emit_posthog_called() -> None:
    mock_capture = MagicMock()
    with patch("app.advisor.monitoring.telemetry._emit_supabase", new_callable=AsyncMock):
        with patch("app.advisor.analytics.events.capture_telemetry", mock_capture):
            with patch("app.advisor.monitoring.telemetry._emit_prometheus"):
                with patch("app.advisor.monitoring.telemetry._emit_sentry"):
                    with patch("app.advisor.monitoring.telemetry._emit_structured_log"):
                        await emit("tool_timeout", "sess-2", metadata={"tool": "crm_create_lead"})
    mock_capture.assert_called_once()
    assert mock_capture.call_args[0][1] == "tool_timeout"
