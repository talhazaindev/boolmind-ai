"""Evidence-first hypothesis generation — wholesale retention scenario."""

from __future__ import annotations

from app.advisor.pipeline.hypothesis_engine import (
    build_hypothesis_evidence_question,
    generate_evidence_hypotheses,
    hypothesis_relevance_violations,
)
from app.advisor.pipeline.question_value import compose_evidence_question
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

WHOLESALE_MESSAGE = (
    "We're a mid-sized wholesale distributor supplying restaurants and grocery chains. "
    "Revenue is up 18% year-over-year, but customer retention has dropped from 92% "
    "to 81% over the last two quarters. Sales says pricing is the problem, operations "
    "says fulfillment reliability is slipping, and customer service believes response "
    "times are driving dissatisfaction. We process around 4,000 orders per week across "
    "three distribution centers."
)

GENERIC_CONTAMINATED_QUESTION = (
    "Which operational metric has shifted most recently — labor cost, utilization, "
    "reimbursement timing, denial rates, or operating expenses?"
)

_FORBIDDEN_TERMS = (
    "reimbursement",
    "denial rate",
    "denial rates",
    "labor cost",
    "claim denial",
)


def _meta() -> SessionMetadata:
    return SessionMetadata()


def _snapshot() -> HypothesisSnapshot:
    return HypothesisSnapshot()


def test_wholesale_extracts_stakeholder_hypotheses() -> None:
    hyps = generate_evidence_hypotheses(
        _meta(), _snapshot(), message=WHOLESALE_MESSAGE
    )
    labels = " ".join(h.label.lower() for h in hyps)
    assert "pricing" in labels
    assert "fulfillment" in labels
    assert "response" in labels


def test_wholesale_evidence_question_uses_stated_theories() -> None:
    q = build_hypothesis_evidence_question(
        _meta(), _snapshot(), message=WHOLESALE_MESSAGE
    )
    assert q is not None
    lower = q.lower()
    assert any(t in lower for t in ("pricing", "fulfillment", "response"))
    for term in _FORBIDDEN_TERMS:
        assert term not in lower


def test_compose_evidence_question_wholesale_not_generic_fallback() -> None:
    q = compose_evidence_question(
        ConversationContextGraph(),
        _snapshot(),
        _meta(),
        message=WHOLESALE_MESSAGE,
    )
    assert q is not None
    assert q != GENERIC_CONTAMINATED_QUESTION
    lower = q.lower()
    for term in _FORBIDDEN_TERMS:
        assert term not in lower


def test_generic_contaminated_question_flagged() -> None:
    violations = hypothesis_relevance_violations(
        GENERIC_CONTAMINATED_QUESTION,
        _meta(),
        _snapshot(),
        message=WHOLESALE_MESSAGE,
    )
    assert any("template_contamination" in v for v in violations)
