"""Validate follow-up questions against known facts and discovery state."""

from __future__ import annotations

import re

from app.advisor.orchestrator.signals import get_signal_registry
from app.advisor.orchestrator.signals.v1 import INFORMATION_GAIN_QUESTIONS
from app.advisor.pipeline.domain_consistency import sanitize_question_for_domain
from app.advisor.pipeline.question_value import (
    compose_evidence_question,
    is_acceptable_discovery_question,
    question_value_violations,
)
from app.advisor.types import HypothesisSnapshot, SessionMetadata

_TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "scale": (
        r"volume",
        r"per day",
        r"per week",
        r"how many",
        r"how much volume",
        r"roughly what volume",
    ),
    "bottleneck": (
        r"which step",
        r"most delay",
        r"where do delays",
        r"get stuck",
    ),
    "integration": (
        r"which system",
        r"erp",
        r"manual routing",
    ),
    "business_context": (
        r"typical workflow",
        r"what does a typical",
    ),
    "compliance_process": (
        r"compliance team priorit",
        r"rule-based system",
        r"manual compliance",
        r"compliance reviews are manual",
    ),
    "compliance_prioritization": (
        r"prioritiz",
        r"fifo",
        r"risk tier",
        r"reviewed first",
        r"which applications get",
    ),
    "backlog_composition": (
        r"percentage.*backlog",
        r"waiting for compliance",
        r"missing documentation",
    ),
    "exception_types": (
        r"types of exceptions",
        r"exceptions caused",
        r"manual intervention",
    ),
    "workflow_steps": (
        r"which steps are manual",
        r"walk me through",
        r"from intake",
    ),
    "timeline": (
        r"first notice this shift",
        r"which quarter or month",
        r"when did you first",
        r"roughly which quarter",
    ),
    "profitability": (
        r"most profitable",
        r"profit or cost",
        r"margin per",
        r"food cost",
        r"unit economics",
    ),
    "order_flow": (
        r"orders flow",
        r"orders flowing",
        r"order-taking",
        r"which table",
        r"dine-in",
        r"takeout",
        r"delivery",
        r"mistakes or delays",
    ),
    "inventory_tracking": (
        r"track stock",
        r"stock levels",
        r"run out or over-order",
        r"stockout",
        r"over-order key",
    ),
    "tools_stack": (
        r"digital tools",
        r"currently in use",
        r"entirely manual",
    ),
    "demand_forecast": (
        r"forecast demand",
        r"weekends or special",
    ),
    "solution_prioritization": (
        r"automate first",
        r"automate one workflow",
        r"had to pick one",
        r"highest-impact starting point",
    ),
    "readiness_constraints": (
        r"practical rollout",
        r"budget range",
        r"busy season",
        r"workflows familiar",
    ),
}

_GENERIC_QUESTION_PATTERNS: tuple[str, ...] = (
    r"what tools do you use",
    r"what are your goals",
    r"tell me more about your business",
    r"what challenges are you facing",
    r"can you tell me more",
)


def question_topic_for_text(question: str | None) -> str | None:
    """Map question text to a discovery topic key."""
    if not question:
        return None
    from app.advisor.pipeline.progress_questions import is_solution_prioritization_question

    if is_solution_prioritization_question(question):
        return "solution_prioritization"
    q = question.lower().strip()
    for key, text in INFORMATION_GAIN_QUESTIONS.items():
        if text.strip().lower() == q or text[:40].lower() in q:
            return key
    signals = get_signal_registry()
    for key, text in signals.unknown_to_question.items():
        if text and text[:40].lower() in q:
            return key
    for topic, patterns in _TOPIC_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q, re.I):
                return topic
    return "custom"


def known_discovery_topics(
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: object | None = None,
) -> set[str]:
    """Topics already satisfied — do not ask again."""
    from app.advisor.pipeline.scale_context import scale_is_satisfied

    known: set[str] = set(meta.answered_question_keys)
    known.update(meta.skipped_question_keys)
    known.update(snapshot.resolved_unknowns)

    facts_blob = " ".join(snapshot.confirmed_facts).lower()
    memory_blob = " ".join(
        f"{line.key}={line.value}" for line in meta.business_memory_lines
    ).lower()
    blob = f"{facts_blob} {memory_blob}"

    if scale_is_satisfied(
        meta,
        snapshot,
        message=message,
        history=history,
        graph=graph,  # type: ignore[arg-type]
    ):
        known.add("scale")
    if snapshot.primary_bottleneck or "bottleneck" in snapshot.resolved_unknowns:
        known.add("bottleneck")
    if snapshot.system_context or "integration" in snapshot.resolved_unknowns:
        known.add("integration")
    if snapshot.active_business_vertical or meta.industry:
        known.add("business_context")
    if any(p in blob for p in ("manual compliance", "compliance reviews are manual", "compliance is manual")):
        known.add("compliance_process")
    if any(p in blob for p in ("fifo", "prioritiz", "risk tier", "reviewed first")):
        known.add("compliance_prioritization")
    if "backlog" in blob:
        known.add("backlog_size")
    if any(p in blob for p in ("automation failed", "prior automation", "poor adoption")):
        known.add("automation_history")

    from app.advisor.pipeline.question_ledger import detect_answered_topics_from_context

    hist_blob = " ".join(history or []).lower()
    ctx_blob = f"{blob} {message.lower()} {hist_blob}"
    known.update(detect_answered_topics_from_context(ctx_blob))

    return known


def is_generic_question(question: str) -> bool:
    q = question.lower().strip()
    signals = get_signal_registry()
    if any(phrase in q for phrase in signals.generic_phrases):
        return True
    return any(re.search(pat, q, re.I) for pat in _GENERIC_QUESTION_PATTERNS)


def question_violations(
    question: str | None,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    graph: object | None = None,
    *,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    """Return violation codes for a proposed follow-up question."""
    if not question:
        return []
    violations: list[str] = []
    topic = question_topic_for_text(question)
    known = known_discovery_topics(snapshot, meta, message=message, history=history, graph=graph)  # type: ignore[arg-type]

    violations.extend(
        question_value_violations(
            question,
            snapshot,
            meta,
            graph,  # type: ignore[arg-type]
            message=message,
            history=history,
        )
    )

    if topic and topic in known and topic not in (
        "solution_prioritization",
        "readiness_constraints",
    ):
        violations.append(f"topic_already_known:{topic}")
    if is_generic_question(question):
        violations.append("question_is_generic")

    q = question.lower()
    facts_blob = " ".join(snapshot.confirmed_facts).lower()

    if re.search(r"volume|per day|per week", q, re.I):
        if snapshot.scale_indicators or "scale" in known:
            violations.append("scale_already_answered")
    if "which step creates the most delay" in q:
        if "planning" in facts_blob or snapshot.primary_bottleneck:
            violations.append("bottleneck_already_implied")
    if topic and topic in meta.open_question_keys and meta.consecutive_question_turns < 2:
        violations.append(f"question_still_open:{topic}")

    return violations


def select_replacement_question(
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    exclude_topics: set[str] | None = None,
    message: str = "",
    history: list[str] | None = None,
    graph: object | None = None,
) -> str | None:
    """Pick highest-value question targeting unresolved topics only."""
    evidence = compose_evidence_question(
        graph,  # type: ignore[arg-type]
        snapshot,
        meta,
        message=message,
        history=history,
    )
    if evidence and is_acceptable_discovery_question(
        evidence, snapshot, meta, graph  # type: ignore[arg-type]
    ):
        return evidence

    from app.advisor.pipeline.question_selector import select_escalation_question

    return select_escalation_question(snapshot, meta, exclude_topics=exclude_topics)


def validate_follow_up_question(
    question: str | None,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    graph: object | None = None,
    message: str = "",
    history: list[str] | None = None,
) -> tuple[str | None, list[str]]:
    """Return (validated_question, violations). Replaces invalid questions."""
    if question:
        sanitized = sanitize_question_for_domain(
            question,
            meta,
            snapshot,  # type: ignore[arg-type]
            message=message,
            history=history,
            graph=graph,  # type: ignore[arg-type]
        )
        if sanitized:
            question = sanitized

    violations = question_violations(question, snapshot, meta, graph, message=message, history=history)
    if not violations or not question:
        return question, violations

    exclude = {v.split(":", 1)[1] for v in violations if ":" in v}
    exclude.update(known_discovery_topics(snapshot, meta))
    replacement = select_replacement_question(
        snapshot,
        meta,
        exclude_topics=exclude,
        message=message,
        history=history,
        graph=graph,
    )
    if replacement and replacement.strip() != (question or "").strip():
        rep_violations = question_violations(replacement, snapshot, meta, graph)
        if not rep_violations:
            return replacement, violations + ["replaced_invalid_question"]
    return None, violations
