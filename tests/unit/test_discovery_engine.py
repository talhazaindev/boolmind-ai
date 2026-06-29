"""Evidence-driven discovery engine tests."""

from __future__ import annotations

from app.advisor.pipeline.discovery_engine import (
    discovery_violations,
    run_discovery,
    select_discovery_question,
)
from app.advisor.pipeline.evidence_extractor import extract_fact_graph
from app.advisor.pipeline.question_value import compose_evidence_question
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

WHOLESALE_MESSAGE = (
    "We're a mid-sized wholesale distributor supplying restaurants and grocery chains. "
    "Revenue is up 18% year-over-year, but customer retention has dropped from 92% "
    "to 81% over the last two quarters. Sales says pricing is the problem, operations "
    "says fulfillment reliability is slipping, and customer service believes response "
    "times are driving dissatisfaction. We process around 4,000 orders per week across "
    "three distribution centers."
)

DENTAL_MESSAGE = (
    "We're a multi-location dental group with 28 clinics. Revenue is growing, but "
    "profitability has been declining for the last three quarters. Leadership is "
    "divided on the cause. Some think it's staffing costs, others think it's "
    "scheduling inefficiencies, and some believe insurance reimbursement delays "
    "are the real issue."
)

NOVEL_INDUSTRY_MESSAGE = (
    "We run a specialty ceramics studio selling bespoke kiln-fired tiles to architects. "
    "Order volume is up 22% but repeat-spec approvals have fallen from 88% to 71% over "
    "six months. Design says glaze formulation drift is the issue, production blames "
    "kiln temperature inconsistency, and account managers think proof turnaround "
    "times are losing clients."
)

GENERIC_CONTAMINATED = (
    "Which operational metric has shifted most recently — labor cost, utilization, "
    "reimbursement timing, denial rates, or operating expenses?"
)


def _meta() -> SessionMetadata:
    return SessionMetadata()


def _snap() -> HypothesisSnapshot:
    return HypothesisSnapshot()


def test_wholesale_facts_extract_stakeholder_theories() -> None:
    graph = extract_fact_graph(_meta(), _snap(), message=WHOLESALE_MESSAGE)
    theories = graph.facts_by_category("stakeholder_theory")
    assert len(theories) >= 3
    theory_text = " ".join(t.text.lower() for t in theories)
    assert "pricing" in theory_text
    assert "fulfillment" in theory_text
    assert "response" in theory_text


def test_wholesale_dynamic_hypotheses_no_catalog_ids() -> None:
    state = run_discovery(_meta(), _snap(), message=WHOLESALE_MESSAGE)
    assert len(state.hypotheses) >= 3
    labels = " ".join(h.label.lower() for h in state.hypotheses)
    assert "pricing" in labels
    assert "fulfillment" in labels
    assert not any(h.id == "reimbursement_delay" for h in state.hypotheses)


def test_wholesale_discriminative_question() -> None:
    state = run_discovery(_meta(), _snap(), message=WHOLESALE_MESSAGE)
    q, gain = select_discovery_question(state)
    assert q is not None
    assert gain >= 0.85
    lower = q.lower()
    assert "changed most materially" in lower
    assert "reimbursement" not in lower
    assert "denial" not in lower


def test_dental_uses_user_theories_not_catalog() -> None:
    state = run_discovery(_meta(), _snap(), message=DENTAL_MESSAGE)
    labels = " ".join(h.label.lower() for h in state.hypotheses)
    assert "staffing" in labels
    assert "scheduling" in labels
    assert "reimbursement" in labels


def test_novel_industry_without_catalog_definitions() -> None:
    """Studio/ceramics scenario — no predefined causes required."""
    state = run_discovery(_meta(), _snap(), message=NOVEL_INDUSTRY_MESSAGE)
    assert len(state.hypotheses) >= 3
    labels = " ".join(h.label.lower() for h in state.hypotheses)
    assert "glaze" in labels or "formulation" in labels
    assert "kiln" in labels or "temperature" in labels
    assert "proof" in labels or "turnaround" in labels
    q, _ = select_discovery_question(state)
    assert q is not None
    assert "reimbursement" not in q.lower()
    assert "denial" not in q.lower()


def test_contaminated_template_rejected() -> None:
    violations = discovery_violations(
        GENERIC_CONTAMINATED, _meta(), _snap(), message=WHOLESALE_MESSAGE
    )
    assert any("template_contamination" in v for v in violations)


def test_compose_evidence_wholesale() -> None:
    q = compose_evidence_question(
        ConversationContextGraph(), _snap(), _meta(), message=WHOLESALE_MESSAGE
    )
    assert q is not None
    assert q != GENERIC_CONTAMINATED


def test_wholesale_turn_pipeline() -> None:
    result = TurnPipeline.run(SessionMetadata(message_count=1), WHOLESALE_MESSAGE, [])
    q = (result.snapshot.required_question or "").lower()
    assert q
    assert "reimbursement" not in q
    assert "denial" not in q
    assert any(t in q for t in ("pricing", "fulfillment", "response"))


def test_tension_detects_competing_explanations() -> None:
    state = run_discovery(_meta(), _snap(), message=WHOLESALE_MESSAGE)
    assert any(t.kind == "competing_explanations" for t in state.tensions)
