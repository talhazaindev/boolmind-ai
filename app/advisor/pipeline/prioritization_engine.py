"""Opportunity cost prioritization — focus and ranking, not readiness gating."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessDriver,
    BusinessModelProfile,
    CausalGraph,
    EvidenceStrength,
    OpportunityCostAssessment,
)
from app.advisor.pipeline.economics_engine import driver_impact_score, impact_weights_for_drivers

_URGENCY_KEYWORDS = ("urgent", "critical", "severe", "major", "35%", "40%", "50%")


def rank_issues_by_opportunity_cost(
    causal_graph: CausalGraph,
    drivers: list[BusinessDriver],
    business_model: BusinessModelProfile,
) -> list[OpportunityCostAssessment]:
    weights = impact_weights_for_drivers(drivers)
    assessments: list[OpportunityCostAssessment] = []

    for node in causal_graph.nodes:
        if node.kind not in ("cause", "outcome", "symptom"):
            continue
        impact_scores = [driver_impact_score(d) for d in node.business_drivers] or [driver_impact_score("revenue_growth")]
        biz_impact = max(s.weighted_total(weights) for s in impact_scores)
        label_lower = node.label.lower()
        urgency = 0.5
        if any(k in label_lower for k in _URGENCY_KEYWORDS):
            urgency = 0.85
        if "churn" in label_lower or "retention" in label_lower:
            urgency = 0.9
        if "scheduling" in label_lower and "5%" in label_lower:
            urgency = 0.2
        if any(k in label_lower for k in ("compensation", "incentive", "organizational", "impact of")):
            urgency = 0.92
        confidence = node.confidence
        opp_cost = round(biz_impact * urgency * confidence, 3)
        assessments.append(
            OpportunityCostAssessment(
                issue_id=node.id,
                label=node.label,
                business_impact_score=biz_impact,
                urgency_score=urgency,
                confidence_score=confidence,
                opportunity_cost=opp_cost,
                linked_driver=node.business_drivers[0] if node.business_drivers else "revenue_growth",
                evidence_strength=node.evidence_strength,
            )
        )

    assessments.sort(key=lambda a: a.opportunity_cost, reverse=True)
    return assessments
