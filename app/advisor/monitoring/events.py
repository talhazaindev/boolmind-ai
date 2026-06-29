"""Telemetry event taxonomy and PII sanitization."""

from __future__ import annotations

import copy
import re
from typing import Any

# Tool lifecycle
TOOL_INVOKED = "tool_invoked"
TOOL_COMPLETED = "tool_completed"
TOOL_TIMEOUT = "tool_timeout"
TOOL_FAILED = "tool_failed"
TOOL_GATED = "tool_gated"

# Turn / LLM
TURN_COMPLETED = "turn_completed"
LLM_RATE_LIMITED = "llm_rate_limited"
EVALUATOR_FALLBACK = "evaluator_fallback"

# Failed operations
FAILED_OPERATION_QUEUED = "failed_operation_queued"
FAILED_OPERATION_RETRIED = "failed_operation_retried"

# Product events (also in analytics)
ARCHITECTURE_ACTIVATED = "architecture_activated"
FIDP_GENERATED = "fidp_generated"

# Execution engine
ROUTER_DECISION = "router_decision"
RESPONSE_QUALITY = "response_quality"
EVAL_QUEUED = "eval_queued"
CONFLICT_DETECTED = "conflict_detected"
CONFLICT_RESOLVED = "conflict_resolved"
STAGE_ADVANCED = "stage_advanced"
MODE_SELECTED = "mode_selected"
TOOL_PLANNED = "tool_planned"
EVAL_SKIPPED = "eval_skipped"
INTERNAL_REASONING = "internal_reasoning"

# Intelligence upgrade
ARCHETYPE_MATCHED = "archetype_matched"
DIAGNOSTIC_DEPTH_UPDATED = "diagnostic_depth_updated"
HYPOTHESIS_QUESTION_SELECTED = "hypothesis_question_selected"
OUTCOME_FRAMING_APPLIED = "outcome_framing_applied"
SOLUTION_GATE_TRIGGERED = "solution_gate_triggered"

PII_KEYS = frozenset(
    {
        "email",
        "name",
        "phone",
        "phone_number",
        "company",
        "attendee",
        "firstname",
        "lastname",
    }
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _redact_value(key: str, value: Any) -> Any:
    if key.lower() in PII_KEYS:
        return "[redacted]"
    if isinstance(value, str) and _EMAIL_RE.search(value):
        return _EMAIL_RE.sub("[email]", value)
    if isinstance(value, dict):
        return {k: _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Strip PII from telemetry metadata before persistence."""
    if not metadata:
        return {}
    cleaned = copy.deepcopy(metadata)
    for key in list(cleaned.keys()):
        cleaned[key] = _redact_value(key, cleaned[key])
    return cleaned
