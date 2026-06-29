"""Central telemetry emit — fan-out to Supabase, PostHog, Prometheus, Sentry, logs."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.advisor.monitoring import events as ev
from app.advisor.monitoring.prometheus_metrics import (
    record_rate_limit,
    record_tool_call,
    record_turn_duration,
)
from app.advisor.monitoring.rollup import record_rollup
from app.core.config import settings

logger = logging.getLogger(__name__)


def _telemetry_json_logs_enabled() -> bool:
    return settings.debug or settings.telemetry_json_logs


async def emit(
    event_type: str,
    session_id: str,
    *,
    visitor_id: str | None = None,
    product_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    exception: BaseException | None = None,
) -> None:
    """Emit telemetry event to all configured sinks. Never raises."""
    safe_meta = ev.sanitize_metadata(metadata)

    try:
        record_rollup(event_type, safe_meta)
    except Exception as e:
        logger.debug("rollup record failed: %s", e)

    try:
        await _emit_supabase(event_type, session_id, visitor_id, product_id, safe_meta)
    except Exception as e:
        logger.debug("supabase telemetry failed: %s", e)

    try:
        _emit_posthog(event_type, session_id, safe_meta)
    except Exception as e:
        logger.debug("posthog telemetry failed: %s", e)

    try:
        _emit_prometheus(event_type, safe_meta)
    except Exception as e:
        logger.debug("prometheus telemetry failed: %s", e)

    try:
        _emit_sentry(event_type, safe_meta, exception)
    except Exception as e:
        logger.debug("sentry telemetry failed: %s", e)

    try:
        _emit_tool_log(event_type, session_id, safe_meta)
    except Exception as e:
        logger.debug("tool log failed: %s", e)

    try:
        _emit_structured_log(event_type, session_id, visitor_id, product_id, safe_meta)
    except Exception as e:
        logger.debug("structured log failed: %s", e)


async def _emit_supabase(
    event_type: str,
    session_id: str,
    visitor_id: str | None,
    product_id: str | None,
    metadata: dict[str, Any],
) -> None:
    if not settings.supabase_configured:
        return
    from app.advisor.integrations.supabase_client import insert_chat_event

    await insert_chat_event(
        {
            "session_id": session_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "product_id": product_id,
            "metadata": metadata,
        }
    )


def _emit_posthog(event_type: str, session_id: str, metadata: dict[str, Any]) -> None:
    from app.advisor.analytics import events as analytics

    props = {"event_type": event_type, **metadata}
    analytics.capture_telemetry(session_id, event_type, props)


def _emit_prometheus(event_type: str, metadata: dict[str, Any]) -> None:
    tool = metadata.get("tool", "unknown")
    if event_type == ev.TOOL_COMPLETED:
        record_tool_call(tool, "success", float(metadata.get("duration_ms", 0)))
    elif event_type == ev.TOOL_TIMEOUT:
        record_tool_call(tool, "timeout", float(metadata.get("duration_ms", 0)))
    elif event_type == ev.TOOL_FAILED:
        record_tool_call(tool, "error", float(metadata.get("duration_ms", 0)))
    elif event_type == ev.TOOL_GATED:
        record_tool_call(tool, "gated", 0.0)
    elif event_type == ev.TURN_COMPLETED:
        record_turn_duration(float(metadata.get("total_ms", 0)))
    elif event_type == ev.LLM_RATE_LIMITED:
        record_rate_limit()


def _emit_sentry(
    event_type: str,
    metadata: dict[str, Any],
    exception: BaseException | None,
) -> None:
    if not settings.sentry_configured:
        return
    if event_type not in (ev.TOOL_FAILED,) and exception is None:
        return
    import sentry_sdk

    tool = metadata.get("tool", "unknown")
    server = metadata.get("server", "unknown")
    outcome = metadata.get("outcome", event_type)
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("tool", tool)
        scope.set_tag("server", server)
        scope.set_tag("outcome", outcome)
        scope.set_context("telemetry", metadata)
        if exception is not None:
            sentry_sdk.capture_exception(exception)
        else:
            sentry_sdk.capture_message(
                f"tool_failed: {tool}",
                level="warning",
            )


_TOOL_LOG_EVENTS = frozenset(
    {
        ev.TOOL_INVOKED,
        ev.TOOL_COMPLETED,
        ev.TOOL_TIMEOUT,
        ev.TOOL_FAILED,
        ev.TOOL_GATED,
    }
)


def _emit_tool_log(
    event_type: str,
    session_id: str,
    metadata: dict[str, Any],
) -> None:
    """Human-readable tool lines in Docker stdout (always on for tool lifecycle)."""
    if event_type not in _TOOL_LOG_EVENTS:
        return
    tool = metadata.get("tool", "unknown")
    server = metadata.get("server", "unknown")
    outcome = metadata.get("outcome", event_type.removeprefix("tool_"))
    duration_ms = metadata.get("duration_ms")
    duration_part = f" duration_ms={duration_ms}" if duration_ms is not None else ""
    logger.info(
        "[advisor.telemetry] event=%s tool=%s server=%s session=%s outcome=%s%s",
        event_type,
        tool,
        server,
        session_id,
        outcome,
        duration_part,
    )


def _emit_structured_log(
    event_type: str,
    session_id: str,
    visitor_id: str | None,
    product_id: str | None,
    metadata: dict[str, Any],
) -> None:
    if not _telemetry_json_logs_enabled():
        return
    payload = {
        "telemetry": True,
        "event_type": event_type,
        "session_id": session_id,
        "visitor_id": visitor_id,
        "product_id": product_id,
        "metadata": metadata,
    }
    logger.info(json.dumps(payload, default=str))
