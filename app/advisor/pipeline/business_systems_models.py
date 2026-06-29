"""Business-systems reasoning ontology — v5 models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceStrength = Literal["observed", "inferred", "speculated"]

BusinessDriver = Literal[
    "revenue_growth",
    "gross_margin",
    "retention",
    "cash_conversion",
    "capacity_utilization",
    "customer_acquisition",
    "risk_exposure",
    "working_capital",
]

UniversalCapability = Literal[
    "acquire_customers",
    "convert_customers",
    "deliver_value",
    "retain_customers",
    "collect_revenue",
    "manage_risk",
    "manage_capacity",
    "manage_information",
    "make_decisions",
]

BusinessMaturity = Literal["EARLY", "GROWING", "SCALING", "MATURE", "ENTERPRISE"]

ConstraintType = Literal[
    "FINANCIAL",
    "ORGANIZATIONAL",
    "REGULATORY",
    "TECHNOLOGICAL",
    "DATA",
    "CULTURAL",
    "TIME",
]

ValueChainStage = Literal[
    "demand_generation",
    "intake",
    "qualification",
    "scheduling",
    "fulfillment",
    "quality_control",
    "billing",
    "retention",
    "reporting",
]

CausalNodeKind = Literal["symptom", "constraint", "cause", "outcome"]
CausalRelation = Literal["causes", "contributes_to", "blocks"]

InterventionType = Literal[
    "PROCESS",
    "POLICY",
    "ORGANIZATIONAL",
    "TECHNOLOGY",
    "AI_AUTOMATION",
]

TechnologyCategory = Literal[
    "PROCESS_ONLY",
    "WORKFLOW_AUTOMATION",
    "CRM",
    "ERP_INTEGRATION",
    "BI_DASHBOARD",
    "SCHEDULING_SYSTEM",
    "DATA_ENGINEERING",
    "FORECASTING_ML",
    "DECISION_AI",
    "CUSTOM_SOFTWARE",
]

ReasoningStage = Literal[
    "DISCOVERY",
    "DIAGNOSIS",
    "VALIDATION",
    "RECOMMENDATION_READINESS",
    "SOLUTION",
]

NarrativeStepType = Literal[
    "clarifying_question",
    "constraint_question",
    "evidence_question",
    "intervention",
]


class IndustryHypothesis(BaseModel):
    label: str
    confidence: float
    evidence_fact_ids: list[str] = Field(default_factory=list)


class BusinessContext(BaseModel):
    operating_model: str | None = None
    inferred_industries: list[IndustryHypothesis] = Field(default_factory=list)
    regulatory_constraints: list[str] = Field(default_factory=list)
    economic_model: str | None = None
    matched_archetype_ids: list[str] = Field(default_factory=list)


class BusinessModelProfile(BaseModel):
    revenue_mechanisms: list[str] = Field(default_factory=list)
    cost_structure: list[str] = Field(default_factory=list)
    scalability_profile: str = "unknown"
    variable_cost_ratio: float | None = None
    fixed_cost_ratio: float | None = None
    margin_sensitivity_drivers: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_strength: EvidenceStrength = "speculated"
    evidence_fact_ids: list[str] = Field(default_factory=list)


class EconomicPriors(BaseModel):
    margin_sensitivity: float = 0.5
    cash_conversion_weight: float = 0.5
    retention_weight: float = 0.5
    model_confidence: float = 0.0


class BusinessPattern(BaseModel):
    pattern_id: str
    label: str
    driver_signature: dict[str, str] = Field(default_factory=dict)
    symptom_signals: list[str] = Field(default_factory=list)
    typical_capability_gaps: list[str] = Field(default_factory=list)
    typical_causal_chains: list[str] = Field(default_factory=list)
    pattern_confidence_threshold: float = 0.55


class PatternMatch(BaseModel):
    pattern: BusinessPattern
    confidence: float
    evidence_fact_ids: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "inferred"


class CapabilitySpecialization(BaseModel):
    universal_id: UniversalCapability
    label: str
    evidence_strength: EvidenceStrength = "inferred"
    confidence: float = 0.0
    evidence_fact_ids: list[str] = Field(default_factory=list)


class CapabilityGap(BaseModel):
    universal_id: UniversalCapability
    specialization_label: str | None = None
    severity: float = 0.0
    evidence_strength: EvidenceStrength = "speculated"
    linked_drivers: list[BusinessDriver] = Field(default_factory=list)
    linked_pattern_ids: list[str] = Field(default_factory=list)
    evidence_fact_ids: list[str] = Field(default_factory=list)


class MaturityAssessment(BaseModel):
    stage: BusinessMaturity = "GROWING"
    confidence: float = 0.0
    evidence_strength: EvidenceStrength = "speculated"
    signals: list[str] = Field(default_factory=list)
    evidence_fact_ids: list[str] = Field(default_factory=list)


class Constraint(BaseModel):
    type: ConstraintType
    description: str
    severity: float = 0.0
    evidence_strength: EvidenceStrength = "speculated"
    evidence_fact_ids: list[str] = Field(default_factory=list)


class ConstraintProfile(BaseModel):
    constraints: list[Constraint] = Field(default_factory=list)
    coverage: float = 0.0
    blocking_types: list[ConstraintType] = Field(default_factory=list)


class ValueChainStageState(BaseModel):
    mode: str | None = None
    notes: str | None = None
    confidence: float = 0.0


class ValueChainState(BaseModel):
    active: bool = False
    breakdown_stage: ValueChainStage | None = None
    stages: dict[str, ValueChainStageState] = Field(default_factory=dict)
    relevance_confidence: float = 0.0
    skip_reason: str | None = None


class StakeholderProfile(BaseModel):
    stakeholder: str
    objectives: list[str] = Field(default_factory=list)
    pressures: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "speculated"
    evidence_fact_ids: list[str] = Field(default_factory=list)


class IncentiveConflict(BaseModel):
    stakeholder_a: str
    stakeholder_b: str
    conflict_reason: str
    severity: float = 0.0
    evidence_strength: EvidenceStrength = "speculated"
    linked_symptom_ids: list[str] = Field(default_factory=list)


class CausalNode(BaseModel):
    id: str
    kind: CausalNodeKind
    label: str
    capability_id: str | None = None
    business_drivers: list[BusinessDriver] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_strength: EvidenceStrength = "speculated"
    evidence_fact_ids: list[str] = Field(default_factory=list)


class CausalEdge(BaseModel):
    source_id: str
    target_id: str
    relation: CausalRelation = "contributes_to"
    confidence: float = 0.0
    uncertainty: float = 1.0


class CausalGraph(BaseModel):
    nodes: list[CausalNode] = Field(default_factory=list)
    edges: list[CausalEdge] = Field(default_factory=list)

    def most_uncertain_edge(self) -> CausalEdge | None:
        if not self.edges:
            return None
        return max(self.edges, key=lambda e: e.uncertainty)

    def root_causes(self) -> list[CausalNode]:
        targets = {e.target_id for e in self.edges}
        return [n for n in self.nodes if n.kind == "cause" and n.id not in targets]


class RootCauseConfidence(BaseModel):
    cause_id: str
    label: str
    confidence: float
    evidence_fact_ids: list[str] = Field(default_factory=list)
    capability_gap_id: str | None = None
    evidence_strength: EvidenceStrength = "speculated"


class ConfidenceState(BaseModel):
    root_causes: list[RootCauseConfidence] = Field(default_factory=list)
    top_confidence: float = 0.0
    validation_ready: bool = False
    competing_within_margin: bool = False


class ImpactWeights(BaseModel):
    revenue: float = 0.25
    margin: float = 0.20
    cash: float = 0.20
    retention: float = 0.15
    risk: float = 0.10
    strategic: float = 0.10


class BusinessImpactScore(BaseModel):
    revenue: float = 0.0
    margin: float = 0.0
    cash: float = 0.0
    retention: float = 0.0
    risk: float = 0.0
    strategic: float = 0.0

    def weighted_total(self, weights: ImpactWeights | None = None) -> float:
        w = weights or ImpactWeights()
        return round(
            self.revenue * w.revenue
            + self.margin * w.margin
            + self.cash * w.cash
            + self.retention * w.retention
            + self.risk * w.risk
            + self.strategic * w.strategic,
            3,
        )


class RecommendationRequirement(BaseModel):
    field: str
    required: bool = True
    confidence_needed: float = 0.6
    evidence_strength_needed: EvidenceStrength = "inferred"


class InterventionTemplate(BaseModel):
    type: InterventionType
    description: str
    typical_impact: BusinessImpactScore = Field(default_factory=BusinessImpactScore)


class InterventionPattern(BaseModel):
    pattern_id: str
    minimum_evidence_requirements: list[RecommendationRequirement] = Field(
        default_factory=list
    )
    typical_interventions: list[InterventionTemplate] = Field(default_factory=list)
    expected_outcomes: list[BusinessImpactScore] = Field(default_factory=list)
    contraindications: list[str] = Field(default_factory=list)


class InterventionCandidate(BaseModel):
    type: InterventionType
    description: str
    target_causal_edge_id: str | None = None
    business_drivers: list[BusinessDriver] = Field(default_factory=list)
    impact: BusinessImpactScore = Field(default_factory=BusinessImpactScore)
    cost: float = 0.0
    complexity: float = 0.0
    time_to_value: float = 0.0
    leverage_score: float = 0.0
    pattern_id: str | None = None


class TechnologyFit(BaseModel):
    category: TechnologyCategory
    confidence: float = 0.0
    rationale: str = ""
    applies_when: str = ""
    not_when: str = ""
    linked_intervention_id: str | None = None


class OpportunityCostAssessment(BaseModel):
    issue_id: str
    label: str
    business_impact_score: float = 0.0
    urgency_score: float = 0.0
    confidence_score: float = 0.0
    opportunity_cost: float = 0.0
    linked_driver: BusinessDriver = "revenue_growth"
    evidence_strength: EvidenceStrength = "speculated"


class RecommendationReadiness(BaseModel):
    root_cause_confidence: float = 0.0
    constraint_coverage: float = 0.0
    intervention_evidence_coverage: float = 0.0
    evidence_strength_floor: EvidenceStrength = "speculated"
    ready: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class NarrativeState(BaseModel):
    primary_driver: BusinessDriver = "revenue_growth"
    business_model_summary: str = ""
    pattern_label: str | None = None
    top_cause: str = ""
    top_cause_confidence: float = 0.0
    top_cause_evidence_strength: EvidenceStrength = "speculated"
    competing_cause: str | None = None
    top_issue_opportunity_cost: float = 0.0
    stakeholder_conflict: str | None = None
    maturity_stage: BusinessMaturity | None = None
    constraint_summary: str | None = None
    value_chain_active: bool = False
    recommended_next_step_type: NarrativeStepType = "clarifying_question"
    recommended_next_step_slot: str = ""


class ExecutiveNarrative(BaseModel):
    narrative_state: NarrativeState = Field(default_factory=NarrativeState)
    prose: str = ""


class BusinessSystemsState(BaseModel):
    pattern_matches: list[PatternMatch] = Field(default_factory=list)
    business_model: BusinessModelProfile = Field(default_factory=BusinessModelProfile)
    economic_priors: EconomicPriors = Field(default_factory=EconomicPriors)
    economic_drivers: list[BusinessDriver] = Field(default_factory=list)
    capabilities: list[CapabilitySpecialization] = Field(default_factory=list)
    capability_gaps: list[CapabilityGap] = Field(default_factory=list)
    maturity: MaturityAssessment = Field(default_factory=MaturityAssessment)
    constraint_profile: ConstraintProfile = Field(default_factory=ConstraintProfile)
    value_chain: ValueChainState = Field(default_factory=ValueChainState)
    stakeholder_profiles: list[StakeholderProfile] = Field(default_factory=list)
    incentive_conflicts: list[IncentiveConflict] = Field(default_factory=list)
    business_context: BusinessContext = Field(default_factory=BusinessContext)
    causal_graph: CausalGraph = Field(default_factory=CausalGraph)
    confidence: ConfidenceState = Field(default_factory=ConfidenceState)
    readiness: RecommendationReadiness = Field(default_factory=RecommendationReadiness)
    opportunity_ranking: list[OpportunityCostAssessment] = Field(default_factory=list)
    intervention_candidates: list[InterventionCandidate] = Field(default_factory=list)
    technology_fits: list[TechnologyFit] = Field(default_factory=list)
    narrative_state: NarrativeState = Field(default_factory=NarrativeState)
    recommended_question: str | None = None
    question_edv_score: float = 0.0
    reasoning_stage: ReasoningStage = "DISCOVERY"
