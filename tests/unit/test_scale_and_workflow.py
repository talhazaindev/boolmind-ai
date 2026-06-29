"""Scale suppression, workflow grounding, and cash-flow discovery tests."""

from app.advisor.orchestrator.diagnostic_trees import locate_universal_stage
from app.advisor.orchestrator.question_append import strip_redundant_questions
from app.advisor.orchestrator.question_composer import compose_contextual_question
from app.advisor.orchestrator.context_graph import build_context_graph
from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.pipeline.question_value import (
    build_cash_flow_evidence_question,
    is_assumed_workflow_stage_question,
    workflow_stage_denied,
)
from app.advisor.pipeline.scale_context import (
    is_volume_probe_question,
    scale_is_satisfied,
    scale_required_for_diagnosis,
)
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

_SAAS_TURN_1 = (
    "We're a B2B software company with about $12M ARR. Revenue is growing around "
    "20% year-over-year, but cash flow has become increasingly unpredictable. "
    "Finance blames sales, sales blames finance, and leadership can't agree on "
    "what's changed."
)

_SAAS_TURN_2 = (
    "A deal gets marked as closed in the CRM, then finance generates an invoice "
    "within 1–3 days. After that, it goes to customers with standard 30-day payment "
    "terms, but we're seeing more delays and disputes before payment clears. "
    "If you're trying to understand where the issue is coming from, it's probably "
    "not intake — it's either invoicing delays, collections, or customer payment "
    "behavior shifting."
)


def test_leadership_does_not_trigger_intake_stage() -> None:
    stage = locate_universal_stage(ConversationContextGraph(), _SAAS_TURN_1.lower())
    assert stage != "intake"


def test_scale_satisfied_with_arr() -> None:
    snap = HypothesisSnapshot()
    meta = SessionMetadata()
    assert scale_is_satisfied(meta, snap, message=_SAAS_TURN_1)
    assert not scale_required_for_diagnosis(meta, snap, None)


def test_volume_probe_detected() -> None:
    assert is_volume_probe_question("Roughly what volume are you handling per day or week?")


def test_workflow_stage_denied_intake() -> None:
    assert workflow_stage_denied(_SAAS_TURN_2.lower(), "intake")


def test_assumed_intake_question_rejected() -> None:
    q = "Walk me through one typical item at the intake step — roughly how long does it sit there?"
    assert is_assumed_workflow_stage_question(q, _SAAS_TURN_2.lower())


def test_cash_flow_evidence_question_turn2() -> None:
    meta = SessionMetadata(message_count=2)
    snap = HypothesisSnapshot()
    q = build_cash_flow_evidence_question(meta, snap, message=_SAAS_TURN_2, history=[_SAAS_TURN_1])
    assert q
    assert "days-to-pay" in q.lower() or "invoice" in q.lower()
    assert "intake step" not in q.lower()


def test_saas_turn1_no_intake_question() -> None:
    result = TurnPipeline.run(SessionMetadata(message_count=1), _SAAS_TURN_1, [])
    q = (result.snapshot.required_question or "").lower()
    assert q
    assert "intake step" not in q
    assert "volume are you handling" not in q


def test_saas_turn2_no_volume_leak() -> None:
    result = TurnPipeline.run(
        SessionMetadata(message_count=2),
        _SAAS_TURN_2,
        [_SAAS_TURN_1],
    )
    q = (result.snapshot.required_question or "").lower()
    assert "volume are you handling" not in q
    assert any(term in q for term in ("invoice", "payment", "dispute", "collect", "cash"))


def test_strip_body_volume_when_appended_question() -> None:
    body = (
        "You're seeing cash flow unpredictability linked to invoicing delays.\n\n"
        "Roughly what volume are you handling per day or week?"
    )
    snap = HypothesisSnapshot(scale_indicators=["$12M ARR"])
    meta = SessionMetadata()
    cleaned = strip_redundant_questions(
        body,
        snap,
        meta,
        appended_question="How have days-to-pay changed recently?",
        message=_SAAS_TURN_1,
    )
    assert "volume are you handling" not in cleaned.lower()
    assert "cash flow unpredictability" in cleaned.lower()
