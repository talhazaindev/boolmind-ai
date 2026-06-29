"""Shared types for the advisor."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConversationStage = Literal["EXPLORE", "INTEREST", "QUALIFY", "CAPTURE", "BOOK", "DONE"]
ProductId = Literal["retify", "ecg", "legal", "forecasting"]
ProductFitId = Literal[
    "retify",
    "ecg",
    "legal",
    "forecasting",
    "custom_solutions",
    "undecided",
]


class ReadinessFlags(BaseModel):
    architecture: bool = False
    product_tour: bool = False
    fidp: bool = False
    lead_capture: bool = False
    booking: bool = False


ConversationMode = Literal["discover", "diagnose", "advise", "recommend", "deliver"]
ExecutionMode = Literal["DISCOVERY", "DIAGNOSE", "SALES", "ARCHITECTURE", "RAG_ONLY"]
DiagnoseDepth = Literal["early", "mid", "late"]
ConversationPipelineStage = Literal[
    "DISCOVERY",
    "CONSTRAINT_MAPPING",
    "BOTTLENECK_ISOLATION",
    "HYPOTHESIS_VALIDATION",
    "SOLUTION_ALIGNMENT",
]
UserSophistication = Literal["low", "medium", "high"]
ReasoningPhase = Literal[
    "discovery",
    "hypothesis_generation",
    "hypothesis_testing",
    "convergence",
    "strategic_insight",
    "solution_exploration",
    "boolmind_positioning",
]
HypothesisStatus = Literal["active", "confirmed", "rejected", "conflicted"]
BusinessModel = Literal[
    "saas",
    "subscription",
    "service",
    "education",
    "local_retail",
    "unknown",
]


class HypothesisState(BaseModel):
    id: str
    label: str
    confidence: float = 0.0
    status: HypothesisStatus = "active"
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)


UniversalWorkflowStage = Literal[
    "intake",
    "preparation",
    "execution",
    "quality_gate",
    "delivery",
    "exception_loop",
    "unknown",
]


class MetricValue(BaseModel):
    value: float | int | str
    unit: str | None = None
    source: str = "user"
    confidence: float = 0.9


class StageState(BaseModel):
    mode: str | None = None
    notes: str | None = None
    confidence: float = 0.0


class PriorAttempt(BaseModel):
    what: str
    outcome: str
    reason: str | None = None


class ConversationContextGraph(BaseModel):
    industry: str | None = None
    problem_dimension: str | None = None
    universal_stage: UniversalWorkflowStage = "unknown"
    workflow_stages: dict[str, StageState] = Field(default_factory=dict)
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    pain_points: list[str] = Field(default_factory=list)
    prior_attempts: list[PriorAttempt] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    user_quote_hooks: list[str] = Field(default_factory=list)
    active_thread: str | None = None
    thread_depth: int = 0
    derived_inferences: list[str] = Field(default_factory=list)


class InternalReasoning(BaseModel):
    observations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    extracted_facts: dict[str, str] = Field(default_factory=dict)
    next_action: Literal[
        "ask_followup", "summarize", "recommend", "pitch"
    ] = "ask_followup"
    top_hypothesis_ids: list[str] = Field(default_factory=list)
    universal_stage: str = "unknown"


class EvidenceEntry(BaseModel):
    turn: int
    text: str
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)


class TurnEvaluation(BaseModel):
    stage: ConversationStage = "EXPLORE"
    profile_updates: dict[str, str | int | float | None] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_discovery_question: str = ""
    readiness: ReadinessFlags = Field(default_factory=ReadinessFlags)
    reasoning: str = ""
    should_recommend: bool = False
    user_sophistication: UserSophistication | None = None


class PageContext(BaseModel):
    title: str = ""
    url: str = ""
    product_id: str | None = None
    product_name: str | None = None


class SessionMetadata(BaseModel):
    is_returning: bool = False
    last_topic: str | None = None
    stage_reached: ConversationStage = "EXPLORE"
    products_discussed: list[str] = Field(default_factory=list)
    visitor_name: str | None = None
    active_product: str | None = None
    top_product: str | None = None
    tech_depth: str = "general"
    collected_email: str | None = None
    message_count: int = 0
    visit_count: int = 0
    crm_captured_emails: list[str] = Field(default_factory=list)
    # Discovery profile (Phase 7)
    business_type: str | None = None
    industry: str | None = None
    pain_point: str | None = None
    goals: str | None = None
    data_context: str | None = None
    constraints: str | None = None
    product_fit: str | None = None
    product_fit_confidence: float = 0.0
    qualification_score: int | None = None
    missing_fields: list[str] = Field(default_factory=list)
    readiness: ReadinessFlags = Field(default_factory=ReadinessFlags)
    consecutive_question_turns: int = 0
    custom_complexity_confirmed: bool = False
    user_sophistication: UserSophistication | None = None
    primary_goal: str | None = None
    problem_dimension: str | None = None
    growth_blocker: str | None = None
    ops_bottleneck: str | None = None
    profit_hypothesis: str | None = None
    workforce_hypothesis: str | None = None
    channels_active: list[str] = Field(default_factory=list)
    # Consulting reasoning state
    reasoning_phase: ReasoningPhase = "discovery"
    business_model: str | None = None
    funnel_stage: str | None = None
    hypotheses: list[HypothesisState] = Field(default_factory=list)
    evidence_log: list[EvidenceEntry] = Field(default_factory=list)
    last_convergence_turn: int = 0
    insight_delivered_turn: int = 0
    # Execution engine state
    catalog_product_fit: str | None = None
    solution_category: str | None = None
    catalog_fit_reasons: list[str] = Field(default_factory=list)
    solution_reasons: list[str] = Field(default_factory=list)
    business_memory_lines: list["ScoredMemoryLine"] = Field(default_factory=list)
    quality_hint_next_turn: bool = False
    quality_failure_count: int = 0
    active_business_vertical: str | None = None
    last_appended_question: str | None = None
    open_question_keys: list[str] = Field(default_factory=list)
    answered_question_keys: list[str] = Field(default_factory=list)
    skipped_question_keys: list[str] = Field(default_factory=list)
    asked_question_fingerprints: list[str] = Field(default_factory=list)
    evidence_score_peak: float = 0.0
    confirmed_bottleneck_count: int = 0
    conflict_hold: bool = False
    context_graph: dict[str, Any] = Field(default_factory=dict)
    active_thread: str | None = None
    active_thread_depth: int = 0
    # Business-systems reasoning v5 state
    business_systems_state: dict[str, Any] = Field(default_factory=dict)
    reasoning_stage: str = "DISCOVERY"
    executive_narrative: dict[str, Any] = Field(default_factory=dict)
    primary_economic_driver: str | None = None
    draft_working_picture_confirmed: bool = False
    last_turn_value: dict[str, object] = Field(default_factory=dict)
    diagnostic_depth: int = 0
    issue_tree: dict[str, Any] = Field(default_factory=dict)
    diagnostic_phase: str = "problem_identification"


class ScoredMemoryLine(BaseModel):
    key: str
    value: str
    confidence: float = 0.0
    source_turn: int = 0
    last_confirmed_turn: int = 0
    contradict_count: int = 0


class HypothesisSnapshot(BaseModel):
    signals_version: str = "v1"
    business_model: str = "unknown"
    active_business_vertical: str | None = None
    primary_bottleneck: str | None = None
    system_context: list[str] = Field(default_factory=list)
    scale_indicators: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    resolved_unknowns: list[str] = Field(default_factory=list)
    unresolved_unknowns: list[str] = Field(default_factory=list)
    conversation_stage: ConversationPipelineStage = "DISCOVERY"
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.5
    confirmed_bottleneck_count: int = 0
    hypothesis_status: HypothesisStatus = "active"
    conflict_detail: str | None = None
    required_question: str | None = None
    diagnose_depth: DiagnoseDepth = "early"
    solutioning_allowed: bool = False


class BusinessMemorySnapshot(BaseModel):
    version: str = "v1"
    lines: tuple[ScoredMemoryLine, ...] = ()


class ProductFitDecision(BaseModel):
    catalog_product_fit: str | None = None
    catalog_reasons: list[str] = Field(default_factory=list)
    solution_category: str | None = None
    solution_reasons: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ToolInvocationPlan(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModeResolution(BaseModel):
    kind: Literal["direct", "blocks_stripped", "tool_cleared"] = "direct"
    trace: list[str] = Field(default_factory=list)


class RouterDecisionRecord(BaseModel):
    intent: str = ""
    intent_confidence: float = 0.0
    routing_confidence: float = 0.0
    tool_confidence: float = 0.0
    execution_mode: ExecutionMode = "DISCOVERY"
    internal_mode: ConversationMode = "discover"
    catalog_product_fit: str | None = None
    catalog_reasons: list[str] = Field(default_factory=list)
    solution_category: str | None = None
    solution_reasons: list[str] = Field(default_factory=list)
    rag_required: bool = False
    tool_selected: str | None = None
    tool_reason: str | None = None
    tool_plan_arguments: dict[str, Any] | None = None
    confidence_gates_applied: list[str] = Field(default_factory=list)
    resolution_trace: list[str] = Field(default_factory=list)
    memory_lines_used: list[str] = Field(default_factory=list)
    evidence_score: float = 0.0
    mode_reasons: list[str] = Field(default_factory=list)


class RouterOutput(BaseModel):
    intent: str
    mode: ExecutionMode
    required_tools: list[str] = Field(default_factory=list)
    tool_plan: ToolInvocationPlan | None = None
    rag_required: bool = False
    routing_confidence: float = 0.0
    tool_confidence: float = 0.0
    internal_mode: ConversationMode = "discover"
    resolution: ModeResolution = Field(default_factory=ModeResolution)
    strip_block_ids: list[str] = Field(default_factory=list)
    product_fit: ProductFitDecision = Field(default_factory=ProductFitDecision)
    decision_record: RouterDecisionRecord = Field(default_factory=RouterDecisionRecord)


class ResponseQualityCheck(BaseModel):
    score: float = 0.0
    passed: bool = True
    failures: list[str] = Field(default_factory=list)


class TurnContext(BaseModel):
    """Immutable execution inputs for a single turn."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    message: str
    history_texts: tuple[str, ...]
    frozen_meta: SessionMetadata
    extracted_meta: SessionMetadata
    snapshot: HypothesisSnapshot
    business_memory: BusinessMemorySnapshot
    product_fit_decision: ProductFitDecision
    router_output: RouterOutput
    grounding_block: str | None = None
    deliverable_block: str | None = None
    rag_status: str = "skipped"
    context_graph: ConversationContextGraph | None = None
    internal_reasoning: InternalReasoning | None = None
    acknowledgment_hints: list[str] = Field(default_factory=list)
    next_question: str | None = None
    turn_value_block: str | None = None
    turn_visual: dict[str, object] | None = None
    turn_plan: Any | None = None
    matched_archetypes: list[Any] = Field(default_factory=list)
    case_evidence: list[dict[str, str]] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] | None = None
    fallback: str | None = None
    duration_ms: float | None = None
    outcome: str | None = None  # success | timeout | error | gated
