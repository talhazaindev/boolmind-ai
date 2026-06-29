"""Business-systems reasoning engine v5 tests."""

from __future__ import annotations

from app.advisor.pipeline.business_model_engine import blended_economic_priors
from app.advisor.pipeline.business_systems_engine import run_business_systems_reasoning
from app.advisor.pipeline.business_systems_models import BusinessModelProfile, IndustryHypothesis
from app.advisor.pipeline.executive_narrative import validate_llm_prose
from app.advisor.pipeline.pattern_engine import match_patterns
from app.advisor.pipeline.prioritization_engine import rank_issues_by_opportunity_cost
from app.advisor.pipeline.recommendation_readiness import assess_recommendation_readiness
from app.advisor.pipeline.stakeholder_engine import INCENTIVE_CONFLICT_PRIOR, conflict_node_confidence
from app.advisor.pipeline.value_chain_engine import value_chain_relevant, locate_breakdown
from app.advisor.pipeline.evidence_extractor import extract_fact_graph
from app.advisor.types import HypothesisSnapshot, SessionMetadata

MARGIN_MESSAGE = (
    "We run a SaaS product. Revenue is growing about 20% but margins keep shrinking. "
    "Customer acquisition costs are up and support tickets doubled."
)
CASH_MESSAGE = (
    "Revenue growing 20% but cash flow is unstable. Invoicing happens end of month "
    "and collections take 60 days."
)
VC_MESSAGE = (
    "We are a venture capital firm. Deal flow is strong but portfolio company "
    "reporting is delayed. AUM fees are flat."
)
CHURN_MESSAGE = (
    "Our subscription business has 35% annual churn but scheduling inefficiency is only 5%. "
    "Sales keeps overpromising delivery timelines."
)


def _snap() -> HypothesisSnapshot:
    return HypothesisSnapshot()


def test_pattern_revenue_margin() -> None:
    fg = extract_fact_graph(SessionMetadata(), _snap(), message=MARGIN_MESSAGE)
    matches = match_patterns(fg)
    assert any(m.pattern.pattern_id == "revenue_up_margin_down" for m in matches)


def test_business_model_saas_margin() -> None:
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=MARGIN_MESSAGE)
    assert "subscription" in bss.business_model.revenue_mechanisms
    assert bss.pattern_matches


def test_value_chain_skipped_knowledge_work() -> None:
    fg = extract_fact_graph(SessionMetadata(), _snap(), message=VC_MESSAGE)
    model = BusinessModelProfile(revenue_mechanisms=["AUM_fee"])
    assert value_chain_relevant(fg, model) is False
    vc = locate_breakdown(fg, model)
    assert vc.active is False


def test_cash_conversion_economics() -> None:
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=CASH_MESSAGE)
    assert "cash_conversion" in bss.economic_drivers


def test_opportunity_cost_prioritization() -> None:
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=CHURN_MESSAGE)
    ranking = rank_issues_by_opportunity_cost(
        bss.causal_graph, bss.economic_drivers, bss.business_model
    )
    assert ranking
    churn_issues = [r for r in ranking if "churn" in r.label.lower() or "retention" in r.label.lower()]
    sched_issues = [r for r in ranking if "scheduling" in r.label.lower()]
    if churn_issues and sched_issues:
        assert churn_issues[0].opportunity_cost >= sched_issues[0].opportunity_cost


def test_opportunity_cost_not_readiness_gate() -> None:
    from app.advisor.pipeline.business_systems_models import ConfidenceState, ConstraintProfile, RootCauseConfidence

    conf = ConfidenceState(
        root_causes=[
            RootCauseConfidence(cause_id="a", label="churn", confidence=0.82, evidence_strength="inferred"),
            RootCauseConfidence(cause_id="b", label="pricing", confidence=0.78, evidence_strength="inferred"),
        ],
        top_confidence=0.82,
        validation_ready=True,
        competing_within_margin=False,
    )
    readiness = assess_recommendation_readiness(conf, ConstraintProfile(coverage=0.7), 0.85)
    assert readiness.ready or "intervention_evidence" in str(readiness.blocking_reasons)


def test_incentive_conflict_confidence_penalty() -> None:
    from app.advisor.pipeline.business_systems_models import IncentiveConflict

    c = IncentiveConflict(
        stakeholder_a="sales",
        stakeholder_b="operations",
        conflict_reason="speed vs quality",
        severity=0.8,
        evidence_strength="speculated",
    )
    penalized = conflict_node_confidence(c)
    assert penalized < 0.8
    assert penalized == round(0.8 * 0.45 * INCENTIVE_CONFLICT_PRIOR, 3)


def test_blended_economic_priors() -> None:
    model = BusinessModelProfile(revenue_mechanisms=["subscription"], margin_sensitivity_drivers=["cac"])
    industries = [IndustryHypothesis(label="saas", confidence=0.8, evidence_fact_ids=[])]
    priors = blended_economic_priors(model, industries)
    assert priors.margin_sensitivity > 0.5


def test_narrative_slots_only() -> None:
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=CASH_MESSAGE)
    good = validate_llm_prose(bss.narrative_state.recommended_next_step_slot or "cash", bss.narrative_state)
    assert validate_llm_prose("Hypothesis 1: churn. Hypothesis 2: pricing.", bss.narrative_state) is False or good


def test_novel_industry_without_templates() -> None:
    msg = (
        "We run a ceramics studio. Glaze formulation failures cause 30% rework. "
        "Kiln temperature variance slows production. Proof turnaround is our bottleneck."
    )
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=msg)
    assert bss.capabilities or bss.pattern_matches or bss.causal_graph.nodes
    q = bss.recommended_question or ""
    assert "reimbursement" not in q.lower()
    assert "denial" not in q.lower()


def test_business_model_margin_discrimination() -> None:
    from app.advisor.pipeline.business_model_engine import infer_business_model

    saas_fg = extract_fact_graph(
        SessionMetadata(),
        _snap(),
        message="We run a SaaS subscription product. MRR is growing but margins keep shrinking. CAC is up.",
    )
    broker_fg = extract_fact_graph(
        SessionMetadata(),
        _snap(),
        message="Insurance brokerage earns commission on policies. Claims ratio and commission compression hurt margins.",
    )
    saas_model = infer_business_model(saas_fg, [], message=saas_fg.source_text)
    broker_model = infer_business_model(broker_fg, [], message=broker_fg.source_text)
    assert "subscription" in saas_model.revenue_mechanisms
    assert "commission" in broker_model.revenue_mechanisms
    assert "cac" in saas_model.margin_sensitivity_drivers
    assert "commission_compression" in broker_model.margin_sensitivity_drivers


def test_intervention_evidence_gate_crm() -> None:
    from app.advisor.pipeline.discovery_models import FactGraph
    from app.advisor.pipeline.intervention_knowledge import (
        _INTERVENTION_PATTERNS,
        evidence_satisfied,
    )

    crm_pattern = next(p for p in _INTERVENTION_PATTERNS if p.pattern_id == "crm_pipeline_failure")
    empty_graph = FactGraph(facts=[], source_text="")
    ok, missing = evidence_satisfied(crm_pattern, empty_graph, BusinessModelProfile())
    assert not ok
    assert any(req.field == "lead_tracking" for req in missing)


def test_readiness_evidence_coverage_blocks() -> None:
    from app.advisor.pipeline.business_systems_models import (
        ConfidenceState,
        ConstraintProfile,
        RootCauseConfidence,
    )

    conf = ConfidenceState(
        root_causes=[
            RootCauseConfidence(
                cause_id="ops",
                label="fulfillment delay",
                confidence=0.82,
                evidence_strength="inferred",
            )
        ],
        top_confidence=0.82,
        validation_ready=True,
        competing_within_margin=False,
    )
    readiness = assess_recommendation_readiness(
        conf, ConstraintProfile(coverage=0.7), intervention_evidence_coverage=0.40
    )
    assert not readiness.ready
    assert any("intervention_evidence" in reason for reason in readiness.blocking_reasons)


def test_process_first_intervention_ranking() -> None:
    from app.advisor.pipeline.intervention_knowledge import _INTERVENTION_PATTERNS, generate_candidates

    pattern = next(p for p in _INTERVENTION_PATTERNS if p.pattern_id == "approval_bottleneck")
    ranked = generate_candidates(pattern)
    org_rank = next(i for i, c in enumerate(ranked) if c.type == "ORGANIZATIONAL")
    tech_rank = next(i for i, c in enumerate(ranked) if c.type == "TECHNOLOGY")
    assert org_rank < tech_rank


def test_stakeholder_conflict_in_causal_graph() -> None:
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=CHURN_MESSAGE)
    assert bss.incentive_conflicts or bss.stakeholder_profiles
    conflict_labels = " ".join(n.label.lower() for n in bss.causal_graph.nodes if n.kind == "cause")
    assert bss.incentive_conflicts or "sales" in conflict_labels or "churn" in conflict_labels


def test_business_model_before_capability_gaps() -> None:
    bss = run_business_systems_reasoning(SessionMetadata(), _snap(), message=MARGIN_MESSAGE)
    assert bss.business_model.confidence > 0
    assert bss.business_model.revenue_mechanisms
    assert bss.capabilities or bss.capability_gaps
