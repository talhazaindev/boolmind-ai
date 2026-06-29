"""Mode selector tests."""

from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.intent_classifier import classify_intent
from app.advisor.pipeline.mode_selector import (
    apply_progression_gates,
    select_execution_mode,
)
from app.advisor.types import SessionMetadata


def test_advice_request_stays_discovery_when_confidence_low() -> None:
    meta = SessionMetadata(industry="logistics", pain_point="delays", goals="improve")
    snap = update_hypothesis_snapshot(meta, "We run a logistics company", [])
    intent = classify_intent("What do you recommend?")
    mode, reasons = select_execution_mode(
        meta, snap, intent, None, "What do you recommend?", []
    )
    assert mode == "DISCOVERY"
    assert snap.overall_confidence < 0.75
    assert any("insufficient_confidence" in r or "advice_request" in r for r in reasons)


def test_advice_request_sales_when_solutioning_allowed() -> None:
    meta = SessionMetadata(
        industry="logistics",
        pain_point="delays",
        evidence_score_peak=0.85,
        message_count=3,
    )
    history = [
        "We dispatch 1500 shipments/day manually. Drivers wait 30-60 minutes.",
    ]
    snap = update_hypothesis_snapshot(meta, "What do you recommend?", history)
    assert snap.solutioning_allowed
    intent = classify_intent("What do you recommend?")
    mode, _ = select_execution_mode(
        meta, snap, intent, None, "What do you recommend?", history
    )
    assert mode == "SALES"


def test_concept_explanation_is_rag_only() -> None:
    meta = SessionMetadata()
    snap = update_hypothesis_snapshot(
        meta, "What does demand planning mean?", []
    )
    intent = classify_intent("What does demand planning mean in plain language?")
    mode, _ = select_execution_mode(
        meta,
        snap,
        intent,
        None,
        "What does demand planning mean in plain language?",
        [],
    )
    assert mode == "RAG_ONLY"


def test_progression_gate_blocks_premature_sales() -> None:
    from app.advisor.types import HypothesisSnapshot

    snap = HypothesisSnapshot(solutioning_allowed=False)
    intent = classify_intent("What do you recommend?")
    mode, gates = apply_progression_gates("SALES", snap, intent)
    assert mode == "DIAGNOSE"
    assert "solutioning_blocked->DIAGNOSE" in gates


def test_low_confidence_does_not_affect_mode_selection() -> None:
    """Mode selection has no confidence input — advisory only."""
    meta = SessionMetadata()
    snap = update_hypothesis_snapshot(meta, "Hi there", [])
    assert snap.overall_confidence < 0.6
    intent = classify_intent("What does demand planning mean?")
    mode, _ = select_execution_mode(
        meta, snap, intent, None, "What does demand planning mean?", []
    )
    assert mode == "RAG_ONLY"
