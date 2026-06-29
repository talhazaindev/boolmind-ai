"""Heuristic response quality — telemetry only, no retry."""

from __future__ import annotations

from app.advisor.constants import DIAGNOSIS_CONFIDENCE_THRESHOLD
from app.advisor.orchestrator.signals import get_signal_registry
from app.advisor.types import DiagnoseDepth, ExecutionMode, HypothesisSnapshot, ResponseQualityCheck

_PASS_THRESHOLD = 0.65

_PREMATURE_SOLUTION_PHRASES = (
    "automation solution",
    "custom automation",
    "custom solution",
    "ai-driven",
    "streamline assignments",
    "route optimization",
    "phased approach starting",
    "exploring automation",
    "boolmind could",
    "we could build",
)

_DIAGNOSE_NATURAL_SIGNALS: tuple[str, ...] = (
    "likely",
    "suggests",
    "because",
    "constraint",
    "tradeoff",
    "backlog",
    "delay",
    "manual",
    "bottleneck",
)


def _has_next_question(body: str) -> bool:
    trimmed = body.rstrip()
    return trimmed.endswith("?") or "Next Question:" in body


def assess_response_quality(
    body: str,
    mode: ExecutionMode,
    snapshot: HypothesisSnapshot,
) -> ResponseQualityCheck:
    failures: list[str] = []
    lower = body.lower()
    signals = get_signal_registry()
    score = 1.0

    if len(body.strip()) < 40:
        failures.append("too_short")
        score -= 0.4

    has_inference = any(
        w in lower for w in ("likely", "suggests", "because", "constraint", "tradeoff")
    )
    if not has_inference:
        failures.append("no_inference")
        score -= 0.2

    anchors = [
        snapshot.business_model,
        snapshot.primary_bottleneck or "",
        *snapshot.system_context,
        *snapshot.scale_indicators,
    ]
    if not any(a and a.lower() in lower for a in anchors):
        failures.append("no_business_anchor")
        score -= 0.15

    for phrase in signals.generic_phrases:
        if phrase in lower:
            failures.append("generic_phrase")
            score -= 0.25
            break

    if mode in ("DISCOVERY", "DIAGNOSE"):
        for phrase in _PREMATURE_SOLUTION_PHRASES:
            if phrase in lower:
                failures.append("premature_solution")
                score -= 0.35
                break
        if not snapshot.solutioning_allowed and any(
            w in lower for w in ("solution", "automate", "implement", "build a system")
        ):
            failures.append("solutioning_not_allowed")
            score -= 0.3
        if mode == "DISCOVERY" or snapshot.overall_confidence < DIAGNOSIS_CONFIDENCE_THRESHOLD:
            for phrase in (
                "you're seeing",
                "you are seeing",
                "clear bottleneck",
                "primary bottleneck is",
                "root cause is",
                "this confirms",
                "the backlog you described",
            ):
                if phrase in lower:
                    failures.append("ungrounded_definitive_assertion")
                    score -= 0.3
                    break
            if "this aligns with" in lower and snapshot.overall_confidence < 0.65:
                failures.append("premature_hypothesis_confirmation")
                score -= 0.2

    if mode == "DIAGNOSE":
        if not any(sig in lower for sig in _DIAGNOSE_NATURAL_SIGNALS):
            failures.append("missing_diagnostic_insight")
            score -= 0.15
        if any(label in body for label in ("Observation:", "Evidence:", "Inference:")):
            failures.append("leaked_diagnose_labels")
            score -= 0.2

    score = max(0.0, min(1.0, score))
    passed = score >= _PASS_THRESHOLD and "generic_phrase" not in failures
    return ResponseQualityCheck(score=score, passed=passed, failures=failures)


def quality_hint_block() -> str:
    return (
        "\nQUALITY_HINT: Prior turn response was too generic. "
        "Anchor inference to BUSINESS_MEMORY facts."
    )
