"""Technology fit reasoning — WHY and WHY NOT."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    ConstraintProfile,
    InterventionCandidate,
    TechnologyCategory,
    TechnologyFit,
)
from app.advisor.pipeline.discovery_models import FactGraph

_TYPE_TO_CATEGORY: dict[str, TechnologyCategory] = {
    "PROCESS": "PROCESS_ONLY",
    "POLICY": "PROCESS_ONLY",
    "ORGANIZATIONAL": "PROCESS_ONLY",
    "TECHNOLOGY": "WORKFLOW_AUTOMATION",
    "AI_AUTOMATION": "DECISION_AI",
}


def annotate_technology_fit(
    candidate: InterventionCandidate,
    fact_graph: FactGraph,
    constraint_profile: ConstraintProfile,
) -> TechnologyFit | None:
    blob = fact_graph.blob()
    category = _TYPE_TO_CATEGORY.get(candidate.type, "WORKFLOW_AUTOMATION")

    if candidate.type in ("PROCESS", "POLICY", "ORGANIZATIONAL"):
        return TechnologyFit(
            category="PROCESS_ONLY",
            confidence=0.85,
            rationale="Process or organizational change addresses constraint before technology",
            applies_when="policy or workflow is the bottleneck",
            not_when="system integration is the root constraint",
            linked_intervention_id=candidate.pattern_id,
        )

    if "crm" in candidate.description.lower() or "lead" in blob:
        category = "CRM"
        rationale = "Lead handoff or pipeline tracking failures"
        not_when = "Process fix not yet attempted" if "approval" in blob else ""
    elif "forecast" in candidate.description.lower() or "demand" in blob:
        category = "FORECASTING_ML"
        rationale = "Demand volatility and inventory waste"
        not_when = "Insufficient historical data" if any(
            c.type == "DATA" for c in constraint_profile.constraints
        ) else ""
    elif "approval" in candidate.description.lower():
        category = "WORKFLOW_AUTOMATION"
        rationale = "Approval queue automation"
        not_when = "Approval is policy-mandated, not capacity-limited"
    elif candidate.type == "AI_AUTOMATION":
        category = "DECISION_AI"
        rationale = "Judgment bottleneck after process options exhausted"
        not_when = "Policy approval requirement should be removed first"
    else:
        rationale = candidate.description
        not_when = ""

    for c in constraint_profile.constraints:
        if c.type == "TECHNOLOGICAL" and "cannot replace" in c.description and category == "ERP_INTEGRATION":
            not_when = "Cannot replace existing platform"
        if c.type == "DATA" and category == "FORECASTING_ML":
            not_when = "Insufficient historical data"

    return TechnologyFit(
        category=category,
        confidence=0.7 if candidate.type == "TECHNOLOGY" else 0.55,
        rationale=rationale,
        applies_when=candidate.description,
        not_when=not_when,
        linked_intervention_id=candidate.pattern_id,
    )
