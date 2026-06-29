"""Question value scoring and evidence-seeking discovery tests."""

from app.advisor.pipeline.question_value import (
    asks_user_to_diagnose,
    binary_hypothesis_choice,
    build_metric_change_question,
    compose_evidence_question,
    extract_competing_causes,
    is_acceptable_discovery_question,
)
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import HypothesisSnapshot, SessionMetadata

_DENTAL_TURN_1 = (
    "We're a multi-location dental group with 28 clinics. Revenue is growing, but "
    "profitability has been declining for the last three quarters. Leadership is "
    "divided on the cause. Some think it's staffing costs, others think it's "
    "scheduling inefficiencies, and some believe insurance reimbursement delays "
    "are the real issue."
)


def test_rejects_binary_hypothesis_question() -> None:
    bad = "To narrow this down - is it more likely ops, or multiple?"
    assert binary_hypothesis_choice(bad)
    assert asks_user_to_diagnose(bad)
    assert not is_acceptable_discovery_question(bad, HypothesisSnapshot(), SessionMetadata())


def test_rejects_bottleneck_delegation_question() -> None:
    bad = "Which system is currently the bottleneck — ERP, manual routing, or coordination?"
    assert asks_user_to_diagnose(bad)
    assert not is_acceptable_discovery_question(bad, HypothesisSnapshot(), SessionMetadata())


def test_extract_competing_causes_dental() -> None:
    causes = extract_competing_causes(_DENTAL_TURN_1.lower())
    assert "staffing_costs" in causes
    assert "scheduling_inefficiency" in causes
    assert "reimbursement_delay" in causes


def test_build_metric_change_question_dental() -> None:
    causes = extract_competing_causes(_DENTAL_TURN_1.lower())
    q = build_metric_change_question(causes, _DENTAL_TURN_1.lower())
    assert q
    assert "three quarters" in q.lower()
    assert "labor costs" in q.lower()
    assert "utilization" in q.lower()
    assert "reimbursement" in q.lower()
    assert "is it more likely" not in q.lower()


def test_dental_pipeline_evidence_question() -> None:
    result = TurnPipeline.run(SessionMetadata(message_count=1), _DENTAL_TURN_1, [])
    q = (result.snapshot.required_question or "").lower()
    assert q
    assert "is it more likely" not in q
    assert "ops, or multiple" not in q
    assert any(
        term in q
        for term in ("changed", "metric", "labor", "utilization", "reimbursement", "quarter")
    )


def test_compose_evidence_question_profitability() -> None:
    meta = SessionMetadata(message_count=1, industry="healthcare")
    snap = HypothesisSnapshot(active_business_vertical="healthcare")
    q = compose_evidence_question(None, snap, meta, message=_DENTAL_TURN_1)
    assert q
    assert is_acceptable_discovery_question(q, snap, meta)
