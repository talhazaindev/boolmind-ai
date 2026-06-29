"""Central business-systems reasoning orchestrator — v5 pipeline."""

from __future__ import annotations

from app.advisor.pipeline.business_model_engine import (
    blended_economic_priors,
    infer_business_model,
)
from app.advisor.pipeline.business_systems_models import (
    BusinessContext,
    BusinessSystemsState,
    ReasoningStage,
)
from app.advisor.pipeline.capability_engine import detect_capability_gaps, infer_capabilities
from app.advisor.pipeline.causal_graph_engine import build_causal_graph
from app.advisor.pipeline.confidence_model import compute_root_cause_confidence
from app.advisor.pipeline.constraint_engine import build_constraint_profile
from app.advisor.pipeline.discovery_engine import select_edv_question
from app.advisor.pipeline.economics_engine import detect_driver_signals, revenue_cash_divergence
from app.advisor.pipeline.evidence_extractor import extract_fact_graph
from app.advisor.pipeline.executive_narrative import generate_executive_narrative
from app.advisor.pipeline.industry_inference import infer_industry_hypotheses, regulatory_priors
from app.advisor.pipeline.intervention_knowledge import (
    compute_intervention_evidence_coverage,
    edv_for_missing_evidence,
    evidence_satisfied,
    match_intervention_patterns,
)
from app.advisor.pipeline.intervention_mapper import rank_interventions
from app.advisor.pipeline.maturity_engine import infer_maturity
from app.advisor.pipeline.pattern_engine import match_patterns
from app.advisor.pipeline.prioritization_engine import rank_issues_by_opportunity_cost
from app.advisor.pipeline.recommendation_readiness import assess_recommendation_readiness
from app.advisor.pipeline.stakeholder_engine import (
    detect_incentive_conflicts,
    extract_stakeholder_profiles,
)
from app.advisor.pipeline.value_chain_engine import locate_breakdown
from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata


def _reasoning_stage(
    confidence_validation: bool,
    readiness_ready: bool,
    has_pattern: bool,
) -> ReasoningStage:
    if readiness_ready:
        return "SOLUTION"
    if confidence_validation:
        return "RECOMMENDATION_READINESS"
    if has_pattern:
        return "DIAGNOSIS"
    return "DISCOVERY"


def run_business_systems_reasoning(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
    matched_archetypes: list[BusinessArchetype] | None = None,
) -> BusinessSystemsState:
    """Full v5 reasoning pass for one turn."""
    fact_graph = extract_fact_graph(
        meta, snapshot, message=message, history=history, graph=graph
    )

    pattern_matches = match_patterns(fact_graph, message=message)
    business_model = infer_business_model(fact_graph, pattern_matches, message=message)
    industries = infer_industry_hypotheses(fact_graph)
    priors = blended_economic_priors(business_model, industries)
    economic_drivers = detect_driver_signals(fact_graph, priors, message=message)
    if revenue_cash_divergence(fact_graph, message=message) and "cash_conversion" not in economic_drivers:
        economic_drivers.append("cash_conversion")

    capabilities = infer_capabilities(fact_graph, message=message)
    capability_gaps = detect_capability_gaps(
        capabilities, fact_graph, pattern_matches, business_model, message=message
    )
    maturity = infer_maturity(fact_graph)

    business_context = BusinessContext(
        operating_model=", ".join(business_model.revenue_mechanisms) or None,
        inferred_industries=industries,
        regulatory_constraints=regulatory_priors(industries),
        economic_model=business_model.scalability_profile,
        matched_archetype_ids=[a.id for a in (matched_archetypes or [])],
    )
    constraint_profile = build_constraint_profile(fact_graph, business_context)
    value_chain = locate_breakdown(fact_graph, business_model)
    stakeholder_profiles = extract_stakeholder_profiles(fact_graph)
    incentive_conflicts = detect_incentive_conflicts(stakeholder_profiles, fact_graph)

    causal_graph = build_causal_graph(
        fact_graph,
        pattern_matches,
        business_model,
        capability_gaps,
        incentive_conflicts,
        value_chain,
        economic_drivers,
    )
    confidence = compute_root_cause_confidence(causal_graph, capability_gaps)
    intervention_coverage = compute_intervention_evidence_coverage(fact_graph, business_model)
    readiness = assess_recommendation_readiness(
        confidence, constraint_profile, intervention_coverage
    )
    opportunity_ranking = rank_issues_by_opportunity_cost(
        causal_graph, economic_drivers, business_model
    )

    intervention_candidates, technology_fits = rank_interventions(
        fact_graph,
        business_model,
        constraint_profile,
        maturity,
        opportunity_ranking,
        readiness.ready,
    )

    bss = BusinessSystemsState(
        pattern_matches=pattern_matches,
        business_model=business_model,
        economic_priors=priors,
        economic_drivers=economic_drivers,
        capabilities=capabilities,
        capability_gaps=capability_gaps,
        maturity=maturity,
        constraint_profile=constraint_profile,
        value_chain=value_chain,
        stakeholder_profiles=stakeholder_profiles,
        incentive_conflicts=incentive_conflicts,
        business_context=business_context,
        causal_graph=causal_graph,
        confidence=confidence,
        readiness=readiness,
        opportunity_ranking=opportunity_ranking,
        intervention_candidates=intervention_candidates,
        technology_fits=technology_fits,
        reasoning_stage=_reasoning_stage(
            confidence.validation_ready,
            readiness.ready,
            bool(pattern_matches),
        ),
    )

    question, edv_score = select_edv_question(bss, fact_graph, meta=meta)
    if not question and readiness.blocking_reasons:
        for reason in readiness.blocking_reasons:
            if "intervention_evidence" in reason:
                patterns = match_intervention_patterns(fact_graph.blob())
                if patterns:
                    _, missing = evidence_satisfied(patterns[0], fact_graph, business_model)
                    question = edv_for_missing_evidence(missing)
                    break
            if "constraint_coverage" in reason and not question:
                question = (
                    "Before recommending changes — are there budget limits, timeline pressures, "
                    "or system constraints we need to work within?"
                )
                break

    bss.recommended_question = question
    bss.question_edv_score = edv_score
    narrative = generate_executive_narrative(bss)
    bss.narrative_state = narrative.narrative_state
    return bss
