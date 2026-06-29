"""Tool planner tests."""

from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.intent_classifier import classify_intent
from app.advisor.pipeline.tool_planner import plan_tool
from app.advisor.types import ProductFitDecision, ReadinessFlags, SessionMetadata


def test_architecture_deferred_in_architecture_mode() -> None:
    meta = SessionMetadata(
        industry="logistics",
        pain_point="manual",
        goals="automate",
        data_context="500 transactions/week",
        business_type="service",
    )
    snap = update_hypothesis_snapshot(
        meta,
        "Can you design a system architecture for our rental marketplace?",
        ["We build a two-sided marketplace"],
    )
    msg = "Can you design a system architecture for our rental marketplace?"
    intent = classify_intent(msg)
    fit = ProductFitDecision(solution_category="custom_solutions", confidence=0.8)
    readiness = ReadinessFlags(architecture=True)
    name, reason, plan, _ = plan_tool(
        "ARCHITECTURE",
        intent,
        False,
        msg,
        meta,
        fit,
        readiness,
        None,
        tool_confidence=0.8,
        legacy_fit="custom_solutions",
    )
    assert name == "generate_architecture_proposal"
    assert plan is not None
    assert plan.tool_name == "generate_architecture_proposal"
