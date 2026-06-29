"""Operations diagnosis — validate before solutions (any business type)."""

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.goal_context import detect_primary_goal
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.orchestrator.operations_diagnosis import (
    build_operations_diagnosis_block,
    detect_bottleneck_hypotheses,
    hypothesis_unvalidated,
    operations_diagnostic_question,
    should_diagnose_operations,
    strategic_tradeoff_insight,
)
from app.advisor.types import ReadinessFlags, SessionMetadata


_FURNITURE_T1 = (
    "I run a small custom furniture manufacturing business. Demand has actually been "
    "increasing, but we're struggling to keep up with orders. Projects are getting "
    "delayed, customers are becoming frustrated, and I'm not sure whether the problem "
    "is our processes, staffing, or something else."
)

_FURNITURE_T2 = (
    "Most delays seem to happen after we receive an order. Some projects move quickly, "
    "while others get stuck waiting for materials or approvals. I'm not sure if we need "
    "better processes, more staff, or better planning."
)


def test_demand_plus_delays_is_operations_not_marketing() -> None:
    meta = SessionMetadata()
    assert detect_primary_goal(meta, _FURNITURE_T1, []) == "operations"


def test_multiple_bottleneck_hypotheses_detected() -> None:
    meta = SessionMetadata(business_type="custom furniture manufacturing")
    hypotheses = detect_bottleneck_hypotheses(meta, _FURNITURE_T2, [_FURNITURE_T1])
    assert "materials" in hypotheses
    assert "approvals" in hypotheses
    assert len(hypotheses) >= 2


def test_unvalidated_hypothesis_triggers_diagnose_mode() -> None:
    meta = SessionMetadata(
        business_type="custom furniture manufacturing",
        pain_point="order delays",
        primary_goal="operations",
        message_count=2,
    )
    history = [_FURNITURE_T1]
    assert hypothesis_unvalidated(meta, _FURNITURE_T2, history) is True
    assert should_diagnose_operations(meta, _FURNITURE_T2, history) is True
    mode = select_conversation_mode(
        _FURNITURE_T2, meta, ReadinessFlags(), history_texts=history
    )
    assert mode == "diagnose"


def test_diagnosis_block_bans_premature_tools() -> None:
    meta = SessionMetadata(
        business_type="custom furniture manufacturing",
        primary_goal="operations",
    )
    block = build_operations_diagnosis_block(meta, _FURNITURE_T2, [_FURNITURE_T1])
    assert "OPERATIONS DIAGNOSIS" in block
    assert "project management" in block.lower() or "software" in block.lower()
    assert "TRADEOFF" in block
    assert "Do NOT recommend" in block


def test_comparative_diagnostic_question_not_tool_suggestion() -> None:
    meta = SessionMetadata(business_type="custom furniture manufacturing")
    q = operations_diagnostic_question(meta, _FURNITURE_T2, [_FURNITURE_T1])
    assert "which causes delays" in q.lower() or "where do projects" in q.lower()
    assert "tool" not in q.lower()
    assert "materials" in q.lower() or "approvals" in q.lower()


def test_tradeoff_explains_wrong_fix() -> None:
    meta = SessionMetadata(business_type="any manufacturing business")
    insight = strategic_tradeoff_insight(meta, _FURNITURE_T2, [_FURNITURE_T1])
    assert "staff" in insight.lower() or "hiring" in insight.lower() or "cost" in insight.lower()


def test_recommendation_block_diagnose_not_pm_tools() -> None:
    meta = SessionMetadata(
        business_type="custom furniture manufacturing",
        primary_goal="operations",
        message_count=2,
    )
    history = [_FURNITURE_T1]
    block = build_recommendation_block(
        meta, "diagnose", user_message=_FURNITURE_T2, history=history
    )
    assert "OPERATIONS DIAGNOSIS" in block
    assert "have you considered" in block.lower() or "Do NOT" in block
