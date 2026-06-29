"""Hypothesis generation adapter — delegates to evidence-driven discovery engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.advisor.pipeline.discovery_engine import (
    discovery_violations,
    hedged_contributor_from_state,
    question_grounds_in_evidence,
    run_discovery,
    select_discovery_question,
)
from app.advisor.pipeline.discovery_models import DynamicHypothesis
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

HypothesisSource = Literal["stakeholder", "symptom", "outcome", "catalog", "inferred"]


@dataclass(frozen=True)
class EvidenceHypothesis:
    id: str
    label: str
    metric: str
    confidence: float
    source: HypothesisSource
    relevance: float


def _to_evidence_hypothesis(h: DynamicHypothesis) -> EvidenceHypothesis:
    source: HypothesisSource = h.source if h.source != "inferred" else "symptom"  # type: ignore[assignment]
    return EvidenceHypothesis(
        id=h.id,
        label=h.label,
        metric=h.metric_phrase,
        confidence=h.confidence,
        source=source,
        relevance=h.evidence_strength,
    )


def generate_evidence_hypotheses(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> list[EvidenceHypothesis]:
    """Dynamic hypotheses from facts — no predefined cause catalog."""
    state = run_discovery(meta, snapshot, message=message, history=history, graph=graph)
    return [_to_evidence_hypothesis(h) for h in state.hypotheses]


def build_hypothesis_evidence_question(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str | None:
    """Highest information-gain discovery question from evidence state."""
    state = run_discovery(meta, snapshot, message=message, history=history, graph=graph)
    question, _gain = select_discovery_question(state)
    return question


def question_tests_top_hypotheses(
    question: str,
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> bool:
    state = run_discovery(meta, snapshot, message=message, history=history, graph=graph)
    return question_grounds_in_evidence(question, state)


def hypothesis_relevance_violations(
    question: str,
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> list[str]:
    return discovery_violations(
        question, meta, snapshot, message=message, history=history, graph=graph
    )


def hedged_contributor_phrase(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str:
    state = run_discovery(meta, snapshot, message=message, history=history, graph=graph)
    return hedged_contributor_from_state(state)
