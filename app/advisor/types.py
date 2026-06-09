"""Shared types for the advisor."""

from typing import Any, Literal

from pydantic import BaseModel, Field

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
UserSophistication = Literal["low", "medium", "high"]


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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] | None = None
    fallback: str | None = None
