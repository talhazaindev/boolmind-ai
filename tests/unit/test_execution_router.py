"""Execution router tests."""

from app.advisor.orchestrator.execution_router import derive_router_output
from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.types import HypothesisSnapshot, ReadinessFlags, SessionMetadata


def _sales_ready_snapshot() -> HypothesisSnapshot:
    return HypothesisSnapshot(
        conversation_stage="SOLUTION_ALIGNMENT",
        overall_confidence=0.85,
        solutioning_allowed=True,
        scale_indicators=["200 shipments/day"],
    )


def test_low_confidence_still_runs_rag_when_required() -> None:
    meta = SessionMetadata()
    snapshot = update_hypothesis_snapshot(
        meta, "What is the difference between Retify and Forecasting?", []
    )
    out = derive_router_output(
        meta,
        snapshot,
        "What is the difference between Retify and Forecasting?",
        ReadinessFlags(),
    )
    assert out.rag_required is True
    assert out.tool_plan is not None
    assert out.tool_plan.tool_name in ("rag_query", "product_compare")


def test_routing_confidence_gate_clears_deliverable_not_rag() -> None:
    meta = SessionMetadata(message_count=1)
    snapshot = update_hypothesis_snapshot(meta, "book a demo please", [])
    out = derive_router_output(
        meta,
        snapshot,
        "book a demo please",
        ReadinessFlags(booking=True),
    )
    if out.routing_confidence < 0.75:
        assert out.tool_plan is None or out.tool_plan.tool_name in ("rag_query", "product_compare")


def test_decision_record_populated() -> None:
    meta = SessionMetadata(industry="logistics", pain_point="delays")
    snapshot = update_hypothesis_snapshot(
        meta, "We run manual dispatch for 200 shipments a day", []
    )
    out = derive_router_output(
        meta,
        snapshot,
        "We run manual dispatch for 200 shipments a day",
        ReadinessFlags(),
    )
    assert out.decision_record.intent
    assert out.decision_record.execution_mode == out.mode


def test_sales_blocked_turn2_low_depth() -> None:
    meta = SessionMetadata(
        message_count=2,
        diagnostic_depth=15,
        industry="logistics",
        data_context="200 shipments/day",
    )
    snapshot = _sales_ready_snapshot()
    out = derive_router_output(
        meta,
        snapshot,
        "we need help with dispatch",
        ReadinessFlags(),
    )
    assert out.mode != "SALES"
    assert any("diagnostic_depth" in g for g in out.decision_record.confidence_gates_applied)


def test_architecture_blocked_low_depth() -> None:
    meta = SessionMetadata(
        message_count=5,
        diagnostic_depth=15,
        industry="logistics",
        data_context="manual dispatch",
    )
    snapshot = HypothesisSnapshot(
        conversation_stage="BOTTLENECK_ISOLATION",
        overall_confidence=0.85,
        solutioning_allowed=False,
        scale_indicators=["manual dispatch"],
    )
    message = "we discussed architecture before — can you draft the proposal now"
    out = derive_router_output(
        meta,
        snapshot,
        message,
        ReadinessFlags(architecture=True),
    )
    assert out.mode != "ARCHITECTURE"


def test_crm_suppressed_below_40() -> None:
    meta = SessionMetadata(
        message_count=8,
        diagnostic_depth=20,
        collected_email="lead@example.com",
        industry="retail",
        pain_point="stockouts",
        data_context="8 staff",
    )
    snapshot = HypothesisSnapshot(
        conversation_stage="DISCOVERY",
        overall_confidence=0.8,
        scale_indicators=["8 staff"],
    )
    message = "my email is lead@example.com please follow up with me"
    out = derive_router_output(
        meta,
        snapshot,
        message,
        ReadinessFlags(lead_capture=True),
    )
    assert out.tool_plan is None or out.tool_plan.tool_name != "crm_create_lead"
    assert any("crm_suppressed" in g for g in out.decision_record.confidence_gates_applied)


def test_diagnose_allowed_mid_depth() -> None:
    meta = SessionMetadata(
        message_count=5,
        diagnostic_depth=45,
        industry="logistics",
        data_context="200 shipments/day",
    )
    snapshot = HypothesisSnapshot(
        conversation_stage="BOTTLENECK_ISOLATION",
        overall_confidence=0.85,
        solutioning_allowed=False,
        scale_indicators=["200 shipments/day"],
    )
    out = derive_router_output(
        meta,
        snapshot,
        "what would you recommend in my situation",
        ReadinessFlags(),
    )
    assert out.mode == "DIAGNOSE"


def test_discovery_forced_below_25() -> None:
    meta = SessionMetadata(
        message_count=4,
        diagnostic_depth=10,
    )
    snapshot = HypothesisSnapshot(
        conversation_stage="BOTTLENECK_ISOLATION",
        overall_confidence=0.85,
        solutioning_allowed=False,
        scale_indicators=["50 orders/day"],
    )
    out = derive_router_output(
        meta,
        snapshot,
        "manual order processing is killing our team",
        ReadinessFlags(),
    )
    assert out.mode == "DISCOVERY"
    assert any("<25->DISCOVERY" in g for g in out.decision_record.confidence_gates_applied)
