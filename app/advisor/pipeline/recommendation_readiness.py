"""Recommendation readiness — safe to recommend gate."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    ConfidenceState,
    ConstraintProfile,
    RecommendationReadiness,
)
from app.advisor.pipeline.intervention_knowledge import compute_intervention_evidence_coverage

ROOT_CAUSE_MIN = 0.72
CONSTRAINT_COVERAGE_MIN = 0.60
INTERVENTION_EVIDENCE_MIN = 0.80


def assess_recommendation_readiness(
    confidence: ConfidenceState,
    constraint_profile: ConstraintProfile,
    intervention_evidence_coverage: float,
) -> RecommendationReadiness:
    blocking: list[str] = []
    top_strength = "speculated"
    if confidence.root_causes:
        top_strength = confidence.root_causes[0].evidence_strength

    if confidence.top_confidence < ROOT_CAUSE_MIN:
        blocking.append(f"root_cause_confidence_{confidence.top_confidence:.2f}")
    if confidence.competing_within_margin:
        blocking.append("competing_causes_within_margin")
    if constraint_profile.coverage < CONSTRAINT_COVERAGE_MIN:
        blocking.append(f"constraint_coverage_{constraint_profile.coverage:.2f}")
    if intervention_evidence_coverage < INTERVENTION_EVIDENCE_MIN:
        blocking.append(f"intervention_evidence_{intervention_evidence_coverage:.2f}")
    if top_strength == "speculated":
        blocking.append("top_cause_speculated_only")

    ready = len(blocking) == 0
    return RecommendationReadiness(
        root_cause_confidence=confidence.top_confidence,
        constraint_coverage=constraint_profile.coverage,
        intervention_evidence_coverage=intervention_evidence_coverage,
        evidence_strength_floor=top_strength,
        ready=ready,
        blocking_reasons=blocking,
    )
