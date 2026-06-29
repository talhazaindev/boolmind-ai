"""Optional value chain diagnostic — only when workflow signals present."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessModelProfile,
    ValueChainStage,
    ValueChainStageState,
    ValueChainState,
)
from app.advisor.pipeline.discovery_models import FactGraph

_OPS_SIGNALS = (
    "dispatch", "backlog", "sla", "fulfillment", "scheduling", "queue",
    "handoff", "production", "inventory", "shipment", "delivery",
)
_KNOWLEDGE_WORK_SIGNALS = (
    "aum", "portfolio", "advisory", "billable hours", "deal flow",
    "underwriting spread", "hedge", "venture", "consulting engagement",
)

_STAGE_SIGNALS: dict[ValueChainStage, tuple[str, ...]] = {
    "demand_generation": ("lead", "marketing", "demand"),
    "intake": ("intake", "application", "order entry", "onboarding"),
    "qualification": ("qualification", "screening", "triage"),
    "scheduling": ("scheduling", "dispatch", "appointment", "planning"),
    "fulfillment": ("fulfillment", "production", "delivery", "execution"),
    "quality_control": ("quality", "review", "compliance check", "qc"),
    "billing": ("billing", "invoice", "payment"),
    "retention": ("retention", "renewal", "churn"),
    "reporting": ("reporting", "dashboard", "forecast", "metrics"),
}


def value_chain_relevant(
    fact_graph: FactGraph,
    business_model: BusinessModelProfile,
) -> bool:
    blob = fact_graph.blob()
    if any(s in blob for s in _KNOWLEDGE_WORK_SIGNALS):
        if not any(s in blob for s in _OPS_SIGNALS):
            return False
    if any(s in blob for s in _OPS_SIGNALS):
        return True
    if business_model.revenue_mechanisms and "project_fee" not in business_model.revenue_mechanisms:
        if "unit_sales" in business_model.revenue_mechanisms:
            return True
    return False


def locate_breakdown(
    fact_graph: FactGraph,
    business_model: BusinessModelProfile,
) -> ValueChainState:
    if not value_chain_relevant(fact_graph, business_model):
        return ValueChainState(
            active=False,
            relevance_confidence=0.2,
            skip_reason="knowledge_work_or_no_ops_signals",
        )

    blob = fact_graph.blob()
    stages: dict[str, ValueChainStageState] = {}
    best_stage: ValueChainStage | None = None
    best_score = 0.0

    for stage, signals in _STAGE_SIGNALS.items():
        hits = [s for s in signals if s in blob]
        if hits:
            conf = min(0.9, 0.3 + 0.15 * len(hits))
            stages[stage] = ValueChainStageState(notes=", ".join(hits), confidence=conf)
            if conf > best_score:
                best_score = conf
                best_stage = stage

    pain_words = ("slow", "bottleneck", "delay", "backlog", "problem", "worst")
    for stage, state in stages.items():
        if any(p in (state.notes or "") for p in pain_words):
            best_stage = stage  # type: ignore[assignment]
            best_score = max(best_score, state.confidence)

    return ValueChainState(
        active=True,
        breakdown_stage=best_stage,
        stages=stages,
        relevance_confidence=round(best_score, 2),
    )
