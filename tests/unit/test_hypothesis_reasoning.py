"""Hypothesis conflict and progression tests."""

from app.advisor.orchestrator.hypothesis_conflict import detect_hypothesis_conflict
from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.execution_router import derive_router_output
from app.advisor.types import ReadinessFlags, ScoredMemoryLine, SessionMetadata


def test_logistics_then_manufacturing_conflict() -> None:
    meta = SessionMetadata(active_business_vertical="logistics")
    memory = [
        ScoredMemoryLine(
            key="business_vertical",
            value="logistics",
            confidence=0.95,
            source_turn=3,
            last_confirmed_turn=3,
        ),
        ScoredMemoryLine(
            key="scale",
            value="1500 shipments/day",
            confidence=0.95,
            source_turn=4,
            last_confirmed_turn=4,
        ),
    ]
    conflicted, detail = detect_hypothesis_conflict(
        "We are a manufacturing company with 40 employees",
        [],
        meta,
        memory,
    )
    assert conflicted is True
    assert detail is not None
    assert "logistics" in detail.lower()
    assert "manufacturing" in detail.lower()


def test_planning_evidence_resolves_bottleneck_unknown() -> None:
    meta = SessionMetadata(industry="logistics", pain_point="delays")
    history = [
        "We run a logistics company",
        "We dispatch around 1,500 shipments per day. Planning is done manually "
        "in spreadsheets by three coordinators. Drivers often wait 30-60 minutes.",
    ]
    snap = update_hypothesis_snapshot(
        meta, history[-1], history[:-1]
    )
    assert "bottleneck" in snap.resolved_unknowns
    assert "planning_delay" in snap.resolved_unknowns
    assert snap.required_question is not None
    assert "which step creates the most delay" not in snap.required_question.lower()
    assert "driver receives which shipment" in snap.required_question.lower()


def test_premature_advice_stays_discovery_until_confidence_met() -> None:
    meta = SessionMetadata(industry="logistics", pain_point="delays")
    snap = update_hypothesis_snapshot(meta, "We run a logistics company", [])
    out = derive_router_output(
        meta, snap, "What do you recommend?", ReadinessFlags()
    )
    assert out.mode == "DISCOVERY"
    assert not snap.solutioning_allowed
    assert snap.overall_confidence < 0.75


def test_advice_with_full_evidence_allows_sales() -> None:
    meta = SessionMetadata(
        industry="logistics",
        pain_point="delays",
        evidence_score_peak=0.85,
        message_count=3,
    )
    history = [
        "We dispatch 1500 shipments per day with manual spreadsheets. "
        "Drivers wait 30-60 minutes.",
    ]
    snap = update_hypothesis_snapshot(meta, "What do you recommend?", history)
    assert snap.conversation_stage == "HYPOTHESIS_VALIDATION"
    assert snap.solutioning_allowed
    out = derive_router_output(
        meta, snap, "What do you recommend?", ReadinessFlags()
    )
    assert out.mode == "SALES"
