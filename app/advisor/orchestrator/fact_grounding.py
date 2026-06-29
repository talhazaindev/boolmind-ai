"""Fact-grounding — separate internal hypotheses from user-facing assertions."""

from __future__ import annotations

import re

from app.advisor.constants import DIAGNOSIS_CONFIDENCE_THRESHOLD
from app.advisor.orchestrator.diagnostic_trees import rank_ops_hypotheses
from app.advisor.types import (
    ConversationContextGraph,
    ExecutionMode,
    HypothesisSnapshot,
    InternalReasoning,
    SessionMetadata,
)

_DEFINITIVE_PHRASES: tuple[str, ...] = (
    "you're seeing",
    "you are seeing",
    "clear bottleneck",
    "clear compliance bottleneck",
    "primary bottleneck is",
    "primary bottleneck",
    "root cause is",
    "this confirms",
    "this aligns with",
    "confirms that",
    "confirms scheduling",
)

_UNGROUNDED_REFERENCE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"backlog you described", "backlog"),
    (r"compliance backlog you described", "backlog"),
    (r"the erp issue", "erp"),
    (r"scheduling problem you", "scheduling"),
)

_HYPOTHESIS_LABELS: dict[str, str] = {
    "queue_saturation": "compliance review queues",
    "exception_handling_gap": "exception handling gaps",
    "manual_handoff": "handoff delays between teams",
    "capacity_ceiling": "analyst capacity limits",
    "data_reentry": "duplicate data entry",
    "prioritization_gap": "unclear prioritization rules",
    "manual_compliance_review": "manual compliance reviews",
    "compliance_queue_backlog": "compliance queue buildup",
    "document_collection_failures": "document collection failures",
}


def user_stated_backlog(
    graph: ConversationContextGraph | None,
    snapshot: HypothesisSnapshot,
) -> bool:
    if graph and "backlog" in graph.metrics:
        return True
    blob = " ".join(snapshot.confirmed_facts).lower()
    return "backlog" in blob


def user_stated_scheduling(blob: str) -> bool:
    return any(
        term in blob.lower()
        for term in ("scheduling", "schedule", "appointment", "calendar")
    )


def collect_user_fact_blob(
    meta: SessionMetadata,
    graph: ConversationContextGraph | None,
    snapshot: HypothesisSnapshot,
) -> str:
    parts = [
        meta.pain_point or "",
        meta.goals or "",
        meta.data_context or "",
        " ".join(snapshot.confirmed_facts),
        " ".join(snapshot.scale_indicators),
    ]
    if graph:
        parts.extend(graph.pain_points)
        parts.extend(graph.user_quote_hooks)
        for key, metric in graph.metrics.items():
            parts.append(f"{key}={metric.value}")
    return " ".join(parts).lower()


def assertion_confidence_allowed(snapshot: HypothesisSnapshot) -> bool:
    return snapshot.overall_confidence >= DIAGNOSIS_CONFIDENCE_THRESHOLD


def build_hedged_contributors(
    graph: ConversationContextGraph,
    snapshot: HypothesisSnapshot,
    *,
    meta: SessionMetadata | None = None,
    message: str = "",
    history: list[str] | None = None,
    max_items: int = 3,
) -> str:
    """External-safe hypothesis summary — never presented as confirmed."""
    if meta is not None:
        from app.advisor.pipeline.discovery_engine import (
            hedged_contributor_from_state,
            run_discovery,
        )

        state = run_discovery(
            meta, snapshot, message=message, history=history, graph=graph
        )
        evidence_phrase = hedged_contributor_from_state(state)
        if evidence_phrase:
            return evidence_phrase

    ranked = rank_ops_hypotheses(graph, snapshot)
    labels: list[str] = []
    for hid, label, conf in ranked[:max_items]:
        if conf < 0.45:
            continue
        human = _HYPOTHESIS_LABELS.get(hid, label.split("—")[0].strip().lower())
        if human not in labels:
            labels.append(human)
    if not labels:
        for hid, conf in sorted(
            snapshot.confidence_scores.items(), key=lambda x: x[1], reverse=True
        )[:max_items]:
            if conf < 0.45 or hid in ("growth", "discovery", "ops"):
                continue
            human = _HYPOTHESIS_LABELS.get(hid, hid.replace("_", " "))
            if human not in labels:
                labels.append(human)
    if not labels:
        return ""
    if len(labels) == 1:
        return f"One possibility is {labels[0]}."
    joined = ", ".join(labels[:-1]) + f", or {labels[-1]}"
    return f"Possible contributors include {joined}."


def build_narrator_grounding_hints(
    graph: ConversationContextGraph,
    snapshot: HypothesisSnapshot,
    reasoning: InternalReasoning,
    meta: SessionMetadata,
    mode: ExecutionMode,
) -> list[str]:
    """Hints the LLM may weave in — hedged unless confidence threshold met."""
    hints: list[str] = []
    if graph.derived_inferences:
        hints.extend(graph.derived_inferences[:2])
    if not assertion_confidence_allowed(snapshot) or mode == "DISCOVERY":
        hedged = build_hedged_contributors(
            graph, snapshot, meta=meta, message=meta.pain_point or ""
        )
        if hedged:
            hints.append(hedged)
        hints.append(
            "Use hedging language only (may indicate, could suggest, one possibility). "
            "Do NOT state root cause or primary bottleneck as fact."
        )
    elif reasoning.inferences:
        hints.append(reasoning.inferences[0])
    return hints[:4]


def _sentence_ungrounded(
    sentence: str,
    fact_blob: str,
    graph: ConversationContextGraph | None,
    snapshot: HypothesisSnapshot,
) -> bool:
    lower = sentence.lower()
    for pattern, required_term in _UNGROUNDED_REFERENCE_PATTERNS:
        if re.search(pattern, lower, re.I):
            if required_term == "backlog" and not user_stated_backlog(graph, snapshot):
                if "backlog" not in fact_blob:
                    return True
            elif required_term not in fact_blob:
                return True
    return False


def _soften_definitive_sentence(sentence: str) -> str:
    s = sentence.strip()
    lower = s.lower()
    replacements = (
        ("you're seeing a clear", "this may involve a"),
        ("you are seeing a clear", "this may involve a"),
        ("you're seeing", "this could reflect"),
        ("you are seeing", "this could reflect"),
        ("the primary bottleneck is", "one possibility is"),
        ("primary bottleneck is", "one possibility is"),
        ("root cause is", "one contributor may be"),
        ("this aligns with", "this could be consistent with"),
        ("this confirms", "this might suggest"),
        ("clear compliance bottleneck", "possible compliance delay"),
        ("clear bottleneck", "possible bottleneck"),
    )
    for old, new in replacements:
        if old in lower:
            idx = lower.index(old)
            s = s[:idx] + new + s[idx + len(old) :]
            lower = s.lower()
    return s


def sanitize_ungrounded_assertions(
    body: str,
    mode: ExecutionMode,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    graph: ConversationContextGraph | None,
) -> str:
    """Remove or soften assertions not supported by user facts or confidence."""
    if not body.strip():
        return body

    fact_blob = collect_user_fact_blob(meta, graph, snapshot)
    allow_definitive = assertion_confidence_allowed(snapshot) and mode != "DISCOVERY"
    paragraphs = re.split(r"\n\n+", body.strip())
    kept: list[str] = []

    for para in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", para.strip())
        cleaned_sents: list[str] = []
        for sent in sentences:
            if not sent.strip():
                continue
            lower = sent.lower()
            if _sentence_ungrounded(sent, fact_blob, graph, snapshot):
                continue
            if not allow_definitive and any(p in lower for p in _DEFINITIVE_PHRASES):
                sent = _soften_definitive_sentence(sent)
            if not allow_definitive and "scheduling is the primary" in lower:
                if not user_stated_scheduling(fact_blob):
                    sent = re.sub(
                        r"scheduling is the primary bottleneck",
                        "scheduling could be one contributor",
                        sent,
                        flags=re.I,
                    )
            cleaned_sents.append(sent)
        if cleaned_sents:
            kept.append(" ".join(cleaned_sents))

    return "\n\n".join(kept).strip()


def question_assumes_unstated_facts(
    question: str,
    graph: ConversationContextGraph,
    snapshot: HypothesisSnapshot,
) -> bool:
    """True when question text references facts the user never provided."""
    q = question.lower()
    if "backlog you described" in q or "backlog you mentioned" in q:
        return not user_stated_backlog(graph, snapshot)
    if "scheduling problem" in q and not user_stated_scheduling(
        collect_user_fact_blob(SessionMetadata(), graph, snapshot)
    ):
        return True
    return False
