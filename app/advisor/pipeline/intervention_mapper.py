"""Intervention ranking — process-first, constraint-filtered."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    ConstraintProfile,
    InterventionCandidate,
    MaturityAssessment,
    OpportunityCostAssessment,
    TechnologyFit,
)
from app.advisor.pipeline.constraint_engine import constraint_blocks_intervention
from app.advisor.pipeline.intervention_knowledge import (
    evidence_satisfied,
    generate_candidates,
    match_intervention_patterns,
)
from app.advisor.pipeline.maturity_engine import maturity_adjusts_intervention_type
from app.advisor.pipeline.technology_fit_engine import annotate_technology_fit

from app.advisor.pipeline.business_systems_models import BusinessModelProfile
from app.advisor.pipeline.discovery_models import FactGraph

_TYPE_PRIORITY = {
    "PROCESS": 5,
    "POLICY": 4,
    "ORGANIZATIONAL": 3,
    "TECHNOLOGY": 2,
    "AI_AUTOMATION": 1,
}


def rank_interventions(
    fact_graph: FactGraph,
    business_model: BusinessModelProfile,
    constraint_profile: ConstraintProfile,
    maturity: MaturityAssessment,
    opportunity_ranking: list[OpportunityCostAssessment],
    readiness_ready: bool,
) -> tuple[list[InterventionCandidate], list[TechnologyFit]]:
    if not readiness_ready:
        return [], []

    patterns = match_intervention_patterns(fact_graph.blob())
    candidates: list[InterventionCandidate] = []
    fits: list[TechnologyFit] = []

    top_issue = opportunity_ranking[0].label if opportunity_ranking else ""

    for pattern in patterns[:2]:
        ok, _ = evidence_satisfied(pattern, fact_graph, business_model)
        if not ok:
            continue
        for cand in generate_candidates(pattern):
            if constraint_blocks_intervention(cand.description, constraint_profile):
                continue
            mult = maturity_adjusts_intervention_type(cand.type, maturity, top_issue)
            type_boost = _TYPE_PRIORITY.get(cand.type, 1)
            cand.leverage_score = round(
                cand.impact.weighted_total() * cand.time_to_value / (1 + cand.cost)
                * mult
                * type_boost
                * 0.15,
                3,
            )
            candidates.append(cand)
            fit = annotate_technology_fit(cand, fact_graph, constraint_profile)
            if fit:
                fits.append(fit)

    candidates.sort(key=lambda c: c.leverage_score, reverse=True)
    return candidates[:3], fits
