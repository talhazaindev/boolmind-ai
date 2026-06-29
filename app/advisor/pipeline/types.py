"""Pipeline layer types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from app.advisor.pipeline.conversation_planner import TurnPlan
from app.advisor.pipeline.turn_value import TurnValueArtifact

if TYPE_CHECKING:
    from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.types import (
    BusinessMemorySnapshot,
    ConversationContextGraph,
    ExecutionMode,
    HypothesisSnapshot,
    InternalReasoning,
    ProductFitDecision,
    ReadinessFlags,
    RouterOutput,
    SessionMetadata,
)


class ExtractedFacts(BaseModel):
    """Read-only facts from current message — no meta mutation."""

    proposed_vertical: str | None = None
    proposed_industry: str | None = None
    proposed_scale: str | None = None
    proposed_employee_count: int | None = None
    proposed_systems: list[str] = Field(default_factory=list)
    claims_fully_automated: bool = False
    claims_manual_process: bool = False


ConflictKind = Literal[
    "vertical_switch",
    "scale_mismatch",
    "automation_claim_vs_manual",
    "system_switch",
]


class ConflictRecord(BaseModel):
    kind: ConflictKind
    prior_value: str
    new_value: str
    severity: Literal["hard", "soft"] = "hard"
    clarification_question: str
    affected_keys: list[str] = Field(default_factory=list)


class ConflictReport(BaseModel):
    is_conflicted: bool = False
    records: list[ConflictRecord] = Field(default_factory=list)
    clarification_question: str | None = None
    blocks_vertical_update: bool = False

    @property
    def conflict_hold(self) -> bool:
        return self.is_conflicted and any(r.severity == "hard" for r in self.records)


class TurnDecisionTrace(BaseModel):
    """Unified explainability record for one turn."""

    pipeline_stage: str = "DISCOVERY"
    funnel_stage: str = "EXPLORE"
    execution_mode: ExecutionMode = "DISCOVERY"
    mode_reasons: list[str] = Field(default_factory=list)
    conflict_hold: bool = False
    evidence_score: float = 0.0
    routing_confidence_advisory: float = 0.0
    readiness: ReadinessFlags = Field(default_factory=ReadinessFlags)
    tool_selected: str | None = None
    tool_reason: str | None = None
    gates_applied: list[str] = Field(default_factory=list)
    gates_rejected: list[str] = Field(default_factory=list)
    memory_lines_used: list[str] = Field(default_factory=list)
    required_question_key: str | None = None
    eval_tier: str = "T0_deterministic"
    active_thread: str | None = None
    universal_stage: str = "unknown"
    top_hypothesis_ids: list[str] = Field(default_factory=list)


class TurnPipelineResult(BaseModel):
    extracted_meta: SessionMetadata
    snapshot: HypothesisSnapshot
    fit_decision: ProductFitDecision
    business_memory: BusinessMemorySnapshot
    readiness: ReadinessFlags
    router_output: RouterOutput
    decision_trace: TurnDecisionTrace
    legacy_fit: str | None = None
    context_graph: ConversationContextGraph | None = None
    internal_reasoning: InternalReasoning | None = None
    turn_value: TurnValueArtifact | None = None
    turn_plan: TurnPlan | None = None
    matched_archetypes: list["BusinessArchetype"] = Field(default_factory=list)
    # Intelligence upgrade — surfaced in SSE done event and telemetry
    matched_archetype_ids: list[str] = Field(default_factory=list)
    archetype_similarity_scores: list[float] = Field(default_factory=list)
    diagnostic_depth: int = 0
    diagnostic_phase: str = "problem_identification"
    issue_tree_snapshot: dict[str, Any] = Field(default_factory=dict)
    turn_plan_priority: str = ""
    case_evidence_retrieved: bool = False
    outcome_framing_applied: bool = False
    hypothesis_question_used: bool = False
