"""Primary goal detection — prevents solution-domain drift."""

from __future__ import annotations

from typing import Literal

from app.advisor.orchestrator.industry_strategy import business_label, rag_industry_guidance_line
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.types import SessionMetadata

PrimaryGoal = Literal["growth_marketing", "operations", "profitability", "workforce", "unknown"]

_GROWTH_SIGNALS: tuple[str, ...] = (
    "grow",
    "growth",
    "growing",
    "more customers",
    "new customers",
    "customer acquisition",
    "discover",
    "discovery",
    "find us",
    "find you",
    "referral",
    "word of mouth",
    "word-of-mouth",
    "stalled",
    "marketing",
    "online presence",
    "social media",
    "online ads",
    "website",
    "limited budget",
    "biggest difference",
    "spend money",
    "visibility",
    "attract",
    "prospects",
    "leads",
    "seo",
    "google business",
)

_OPERATIONS_SIGNALS: tuple[str, ...] = (
    "document management",
    "data pipeline",
    "workflow automation",
    "integrate systems",
    "ocr",
    "etl",
    "data unification",
    "erp integration",
    "internal operations",
    "automate workflow",
    "document processing",
    "delay",
    "delayed",
    "delays",
    "bottleneck",
    "backlog",
    "keep up",
    "struggling",
    "materials",
    "supply chain",
    "staffing",
    "staff",
    "hiring",
    "capacity",
    "workflow",
    "process",
    "processes",
    "scheduling",
    "approval",
    "approvals",
    "production",
    "fulfillment",
    "manufacturing",
    "orders",
)

_OPS_PRIORITY_SIGNALS: tuple[str, ...] = (
    "delay",
    "delayed",
    "delays",
    "bottleneck",
    "backlog",
    "keep up",
    "stuck waiting",
    "materials",
    "approvals",
    "staffing",
    "workflow",
    "frustrated",
)

_GOAL_DRIFT_FIELDS = frozenset({"data_context", "product_fit"})


def _blob(meta: SessionMetadata, message: str, history_texts: list[str]) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        meta.constraints or "",
        meta.primary_goal or "",
        message,
        " ".join(history_texts),
    ]
    return " ".join(parts).lower()


def detect_primary_goal(
    meta: SessionMetadata,
    message: str = "",
    history_texts: list[str] | None = None,
) -> PrimaryGoal:
    if meta.primary_goal in ("growth_marketing", "operations", "profitability", "workforce"):
        return meta.primary_goal  # type: ignore[return-value]

    texts = history_texts or []
    dimension = detect_problem_dimension(meta, message, texts)
    if dimension == "profitability":
        return "profitability"
    if dimension == "workforce":
        return "workforce"
    if dimension == "growth":
        return "growth_marketing"
    if dimension == "throughput":
        return "operations"

    blob = _blob(meta, message, texts)
    growth_hits = sum(1 for s in _GROWTH_SIGNALS if s in blob)
    ops_hits = sum(1 for s in _OPERATIONS_SIGNALS if s in blob)

    ops_priority = sum(1 for s in _OPS_PRIORITY_SIGNALS if s in blob)

    # Strong demand + delivery pain = operations scaling, not marketing
    if "demand" in blob and ops_priority >= 1:
        return "operations"
    if ops_priority >= 1 and ops_hits >= 1:
        return "operations"
    if growth_hits >= 1 and ops_hits == 0:
        return "growth_marketing"
    if ops_hits >= 1 and growth_hits == 0:
        return "operations"
    if ops_hits >= 2:
        return "operations"
    if growth_hits >= 2:
        return "growth_marketing"
    if ops_hits >= 1:
        return "operations"
    if growth_hits >= 1:
        return "growth_marketing"
    return "unknown"


def filter_missing_for_goal(
    missing: list[str],
    primary_goal: PrimaryGoal,
) -> list[str]:
    """Remove fields that cause domain drift when goal is not product qualification."""
    if primary_goal in ("growth_marketing", "profitability", "workforce"):
        return [m for m in missing if m not in _GOAL_DRIFT_FIELDS]
    return missing


def growth_discovery_question(meta: SessionMetadata, message: str = "") -> str:
    label = business_label(meta)
    return (
        f"How do new customers or clients typically find {label} today, "
        f"and which channels matter most besides referrals?"
    )


def operations_discovery_question(
    meta: SessionMetadata,
    message: str = "",
    history_texts: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.operations_diagnosis import operations_diagnostic_question

    return operations_diagnostic_question(meta, message, history_texts or [])


def profitability_discovery_question(
    meta: SessionMetadata,
    message: str = "",
    history_texts: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.profitability_diagnosis import (
        profitability_diagnostic_question,
    )

    return profitability_diagnostic_question(meta, message, history_texts or [])


def workforce_discovery_question(
    meta: SessionMetadata,
    message: str = "",
    history_texts: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.workforce_diagnosis import workforce_diagnostic_question

    return workforce_diagnostic_question(meta, message, history_texts or [])


def goal_lock_prompt_block(primary_goal: PrimaryGoal, meta: SessionMetadata) -> str:
    if primary_goal == "growth_marketing":
        label = business_label(meta)
        return (
            f"\n\nPRIMARY GOAL LOCK: User goal is customer acquisition / growth / marketing "
            f"(NOT internal operations).\n"
            f"- Do NOT ask about document management, data pipelines, or internal workflows "
            f"unless the user explicitly raised them.\n"
            f"- Do NOT route to catalog data products (Retify, ECG, Legal, Forecasting).\n"
            f"- Focus on how prospects find {label} — channel fit, not back-office ops.\n"
            f"- {rag_industry_guidance_line(meta)}"
        )
    if primary_goal == "operations":
        label = business_label(meta)
        return (
            f"\n\nPRIMARY GOAL LOCK: User goal is operational scaling / delivery / workflow "
            f"(NOT marketing or customer acquisition).\n"
            f"- Do NOT pivot to websites, SEO, social media, or lead generation.\n"
            f"- Do NOT recommend tools, software, or hiring until the dominant bottleneck "
            f"is validated for {label}.\n"
            f"- Flow: hypothesis → validation question → tradeoff insight → then solutions.\n"
            f"- Use rag_query(capabilities) for industry-specific ops tactics only AFTER "
            f"bottleneck is confirmed."
        )
    if primary_goal == "profitability":
        label = business_label(meta)
        return (
            f"\n\nPRIMARY GOAL LOCK: User goal is profitability / margins / pricing "
            f"(NOT delivery throughput or customer acquisition).\n"
            f"- Do NOT pivot to delivery delays, materials, production bottlenecks, or hiring.\n"
            f"- Do NOT pivot to websites, SEO, or lead generation.\n"
            f"- Busy team + flat profit = diagnose pricing, utilization, scope creep, or mix.\n"
            f"- Use hypotheses the user stated (pricing, efficiency, etc.) for {label}.\n"
            f"- Flow: metric → hypothesis → validation → tradeoff → then solutions."
        )
    if primary_goal == "workforce":
        label = business_label(meta)
        return (
            f"\n\nPRIMARY GOAL LOCK: User goal is workforce retention / turnover "
            f"(NOT customer acquisition or delivery throughput).\n"
            f"- Do NOT pivot to marketing, enrollment growth tactics, or production bottlenecks.\n"
            f"- Evidence from feedback is NOT confirmed root cause — validate ONE driver.\n"
            f"- Use hypotheses the user stated (compensation, workload, management, etc.).\n"
            f"- Flow: evidence → hypothesis → validation → business insight → then interventions."
        )
    return ""
