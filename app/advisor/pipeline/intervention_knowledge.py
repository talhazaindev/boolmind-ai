"""Intervention patterns with minimum evidence requirements."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessImpactScore,
    BusinessModelProfile,
    InterventionCandidate,
    InterventionPattern,
    InterventionTemplate,
    InterventionType,
    RecommendationRequirement,
)
from app.advisor.pipeline.discovery_models import FactGraph

_INTERVENTION_PATTERNS: list[InterventionPattern] = [
    InterventionPattern(
        pattern_id="approval_bottleneck",
        minimum_evidence_requirements=[
            RecommendationRequirement(field="approval_process", required=True, confidence_needed=0.6),
            RecommendationRequirement(field="approval_volume", required=False, confidence_needed=0.5),
        ],
        typical_interventions=[
            InterventionTemplate(type="PROCESS", description="Remove approval for low-risk items"),
            InterventionTemplate(type="POLICY", description="Define risk-based approval thresholds"),
            InterventionTemplate(type="ORGANIZATIONAL", description="Parallel review lanes"),
            InterventionTemplate(type="TECHNOLOGY", description="Workflow automation for approvals"),
            InterventionTemplate(type="AI_AUTOMATION", description="AI triage for exception routing"),
        ],
        contraindications=["regulatory_mandated_approval"],
    ),
    InterventionPattern(
        pattern_id="cash_conversion_gap",
        minimum_evidence_requirements=[
            RecommendationRequirement(field="invoicing_timing", required=True, confidence_needed=0.55),
            RecommendationRequirement(field="collections_process", required=True, confidence_needed=0.55),
        ],
        typical_interventions=[
            InterventionTemplate(type="PROCESS", description="Redesign invoicing cadence"),
            InterventionTemplate(type="PROCESS", description="Collections workflow with escalation"),
            InterventionTemplate(type="POLICY", description="Adjust payment terms"),
        ],
    ),
    InterventionPattern(
        pattern_id="crm_pipeline_failure",
        minimum_evidence_requirements=[
            RecommendationRequirement(field="lead_tracking", required=True, confidence_needed=0.65),
            RecommendationRequirement(field="handoff_process", required=True, confidence_needed=0.6),
            RecommendationRequirement(field="current_crm_stack", required=True, confidence_needed=0.7),
        ],
        typical_interventions=[
            InterventionTemplate(type="PROCESS", description="Standardize lead handoff checklist"),
            InterventionTemplate(type="TECHNOLOGY", description="CRM pipeline optimization"),
        ],
        contraindications=["no_lead_volume"],
    ),
    InterventionPattern(
        pattern_id="retention_churn",
        minimum_evidence_requirements=[
            RecommendationRequirement(field="churn_rate", required=True, confidence_needed=0.6),
            RecommendationRequirement(field="onboarding_process", required=False, confidence_needed=0.5),
        ],
        typical_interventions=[
            InterventionTemplate(type="PROCESS", description="Onboarding success milestones"),
            InterventionTemplate(type="ORGANIZATIONAL", description="Customer success ownership"),
        ],
    ),
]

_FIELD_SIGNALS: dict[str, tuple[str, ...]] = {
    "approval_process": ("approval", "approve", "sign-off"),
    "approval_volume": ("backlog", "queue", "pending approval"),
    "invoicing_timing": ("invoice", "billing", "invoicing"),
    "collections_process": ("collections", "payment", "receivable", "dso"),
    "lead_tracking": ("lead", "pipeline", "crm"),
    "handoff_process": ("handoff", "hand off", "transfer"),
    "current_crm_stack": ("salesforce", "hubspot", "crm", "spreadsheet"),
    "churn_rate": ("churn", "retention", "leaving"),
    "onboarding_process": ("onboarding", "onboard"),
}


def _field_satisfied(field: str, fact_graph: FactGraph) -> bool:
    blob = fact_graph.blob()
    signals = _FIELD_SIGNALS.get(field, (field.replace("_", " "),))
    return any(s in blob for s in signals)


def match_intervention_patterns(blob: str) -> list[InterventionPattern]:
    matched: list[InterventionPattern] = []
    for pattern in _INTERVENTION_PATTERNS:
        pid = pattern.pattern_id.replace("_", " ")
        if pid.split()[0] in blob or any(
            r.field.replace("_", " ") in blob for r in pattern.minimum_evidence_requirements
        ):
            matched.append(pattern)
    if not matched and ("margin" in blob or "cash" in blob):
        matched.append(_INTERVENTION_PATTERNS[1])
    if not matched and ("approval" in blob or "backlog" in blob):
        matched.append(_INTERVENTION_PATTERNS[0])
    return matched or [_INTERVENTION_PATTERNS[0]]


def evidence_satisfied(
    pattern: InterventionPattern,
    fact_graph: FactGraph,
    business_model: BusinessModelProfile,
) -> tuple[bool, list[RecommendationRequirement]]:
    missing: list[RecommendationRequirement] = []
    for req in pattern.minimum_evidence_requirements:
        if req.required and not _field_satisfied(req.field, fact_graph):
            missing.append(req)
    return len(missing) == 0, missing


def compute_intervention_evidence_coverage(
    fact_graph: FactGraph,
    business_model: BusinessModelProfile,
) -> float:
    patterns = match_intervention_patterns(fact_graph.blob())
    if not patterns:
        return 0.0
    pattern = patterns[0]
    total = len(pattern.minimum_evidence_requirements) or 1
    satisfied = sum(
        1 for r in pattern.minimum_evidence_requirements if _field_satisfied(r.field, fact_graph)
    )
    return round(satisfied / total, 2)


def edv_for_missing_evidence(missing: list[RecommendationRequirement]) -> str | None:
    if not missing:
        return None
    field = missing[0].field.replace("_", " ")
    prompts = {
        "lead tracking": "How are leads tracked today — CRM, spreadsheet, or something else?",
        "handoff process": "When a lead moves from marketing to sales, what does that handoff look like?",
        "current crm stack": "What system do you use to manage customer relationships today?",
        "approval process": "Walk me through how approvals work — who signs off and on what criteria?",
        "invoicing timing": "When do you typically invoice — on delivery, milestone, or end of month?",
        "collections process": "How do you follow up on overdue payments today?",
        "churn rate": "Do you have a rough sense of monthly or annual churn?",
    }
    return prompts.get(field, f"Can you describe your {field} in a bit more detail?")


def generate_candidates(
    pattern: InterventionPattern,
    constraints_ok: bool = True,
) -> list[InterventionCandidate]:
    if not constraints_ok:
        return []
    candidates: list[InterventionCandidate] = []
    type_priority = {"PROCESS": 5, "POLICY": 4, "ORGANIZATIONAL": 3, "TECHNOLOGY": 2, "AI_AUTOMATION": 1}
    for tmpl in pattern.typical_interventions:
        impact = tmpl.typical_impact.weighted_total() or 0.5
        candidates.append(
            InterventionCandidate(
                type=tmpl.type,
                description=tmpl.description,
                business_drivers=["gross_margin"],
                impact=tmpl.typical_impact,
                cost=0.3 if tmpl.type in ("TECHNOLOGY", "AI_AUTOMATION") else 0.15,
                complexity=0.2 if tmpl.type == "PROCESS" else 0.45,
                time_to_value=0.8 if tmpl.type == "PROCESS" else 0.5,
                leverage_score=impact * type_priority.get(tmpl.type, 1) * 0.2,
                pattern_id=pattern.pattern_id,
            )
        )
    candidates.sort(key=lambda c: c.leverage_score, reverse=True)
    return candidates
