"""Detect which business metric the user is optimizing before choosing a diagnostic framework.

Dimensions are generic (growth, throughput, profitability, efficiency, retention) —
not per-industry. User-stated hypotheses (e.g. \"pricing or efficiency\") take priority.
"""

from __future__ import annotations

from typing import Literal

from app.advisor.types import SessionMetadata

ProblemDimension = Literal[
    "growth",
    "throughput",
    "profitability",
    "efficiency",
    "workforce",
    "retention",
    "unknown",
]

_GROWTH_SIGNALS = (
    "grow",
    "growth",
    "more customers",
    "new customers",
    "customer acquisition",
    "discover",
    "discovery",
    "find us",
    "referral",
    "marketing",
    "online presence",
    "visibility",
    "attract",
    "leads",
    "seo",
)

_THROUGHPUT_SIGNALS = (
    "delay",
    "delayed",
    "delays",
    "stuck waiting",
    "get stuck",
    "gets stuck",
    "stuck",
    "backlog",
    "backing up",
    "bottleneck",
    "keep up",
    "can't deliver",
    "cannot deliver",
    "behind schedule",
    "fulfillment",
    "orders piling",
)

_PROFITABILITY_SIGNALS = (
    "profit",
    "profits",
    "profitability",
    "margin",
    "margins",
    "pricing",
    "undercharging",
    "undercharge",
    "haven't increased",
    "hasn't increased",
    "not increased much",
    "flat profit",
    "revenue hasn't",
    "not making more money",
    "bill rate",
    "hourly rate",
    "scope creep",
    "unbilled",
    "low margin",
)

_EFFICIENCY_SIGNALS = (
    "efficiency",
    "inefficien",
    "wasted time",
    "waste time",
    "manual process",
    "repetitive",
    "too much time on",
    "busy work",
)

_RETENTION_SIGNALS = (
    "customer churn",
    "customers leaving",
    "repeat business",
    "coming back",
    "keep customers",
)

_WORKFORCE_SIGNALS = (
    "turnover",
    "quit",
    "quitting",
    "recruiting and training",
    "hard to retain",
    "can't retain",
    "cannot retain",
    "retention problem",
    "employee retention",
    "staff retention",
    "teacher retention",
    "instructor retention",
)

_WORKFORCE_CONTEXT = (
    "teacher",
    "instructor",
    "employee",
    "staff",
    "team member",
    "workforce",
    "recruiting",
    "hiring",
)

_BUSY_SIGNALS = (
    "overwhelmed",
    "busy all the time",
    "constantly busy",
    "swamped",
    "stretched thin",
    "too much work",
)

_USER_HYPOTHESIS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pricing": ("pricing", "price", "undercharg", "rates", "margin"),
    "efficiency": ("efficiency", "inefficien", "wasted", "manual", "repetitive"),
    "throughput": ("delay", "delays", "backlog", "bottleneck", "delivery"),
    "staffing": ("staffing", "hiring", "headcount", "capacity"),
    "compensation": ("compensation", "pay", "salary"),
    "workload": ("workload", "overwhelmed"),
    "management": ("management", "manager"),
    "career_growth": ("career growth", "advancement", "promotion"),
    "retention": ("retention", "churn", "repeat"),
    "growth": ("growth", "more customers", "acquisition"),
}


def _blob(meta: SessionMetadata, message: str, history: list[str] | None) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        message,
        " ".join(history or []),
    ]
    return " ".join(parts).lower()


def _busy_not_profitable(blob: str) -> bool:
    busy = any(s in blob for s in _BUSY_SIGNALS)
    profit_concern = any(s in blob for s in _PROFITABILITY_SIGNALS)
    return busy and profit_concern


def _is_workforce_context(blob: str) -> bool:
    has_issue = any(s in blob for s in _WORKFORCE_SIGNALS) or (
        "turnover" in blob and any(c in blob for c in _WORKFORCE_CONTEXT)
    )
    has_people = any(s in blob for s in _WORKFORCE_CONTEXT)
    workforce_framing = any(
        kw in blob for kw in ("compensation", "workload", "management", "career growth")
    )
    return has_issue and (has_people or workforce_framing)


def detect_user_stated_hypotheses(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    """Hypotheses the user named explicitly — use these in diagnostic questions."""
    blob = _blob(meta, message, history)
    found: list[str] = []
    for category, keywords in _USER_HYPOTHESIS_KEYWORDS.items():
        if any(kw in blob for kw in keywords):
            found.append(category)
    return found


def detect_problem_dimension(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> ProblemDimension:
    if meta.problem_dimension and meta.problem_dimension != "unknown":
        return meta.problem_dimension  # type: ignore[return-value]

    blob = _blob(meta, message, history)
    user_hypotheses = detect_user_stated_hypotheses(meta, message, history)

    growth_hits = sum(1 for s in _GROWTH_SIGNALS if s in blob)
    throughput_hits = sum(1 for s in _THROUGHPUT_SIGNALS if s in blob)
    profit_hits = sum(1 for s in _PROFITABILITY_SIGNALS if s in blob)
    efficiency_hits = sum(1 for s in _EFFICIENCY_SIGNALS if s in blob)
    retention_hits = sum(1 for s in _RETENTION_SIGNALS if s in blob)

    # User names pricing/profit → profitability dimension (even if team is busy)
    if "pricing" in user_hypotheses or profit_hits >= 1:
        if throughput_hits == 0 or profit_hits >= 1 or _busy_not_profitable(blob):
            return "profitability"

    if _busy_not_profitable(blob):
        return "profitability"

    if "efficiency" in user_hypotheses and profit_hits >= 1:
        return "profitability"

    if _is_workforce_context(blob):
        return "workforce"

    if retention_hits >= 1 and growth_hits == 0:
        return "retention"

    if throughput_hits >= 1:
        return "throughput"

    if efficiency_hits >= 1 and profit_hits == 0:
        return "efficiency"

    if growth_hits >= 1:
        return "growth"

    if efficiency_hits >= 1:
        return "efficiency"

    return "unknown"


def dimension_label(dimension: ProblemDimension) -> str:
    labels = {
        "growth": "customer acquisition / growth",
        "throughput": "delivery throughput / fulfillment",
        "profitability": "profitability / margins / pricing",
        "efficiency": "operational efficiency / utilization",
        "workforce": "workforce retention / turnover / engagement",
        "retention": "customer retention / repeat business",
        "unknown": "business performance",
    }
    return labels.get(dimension, "business performance")


def dimension_lock_prompt_block(
    dimension: ProblemDimension,
    meta: SessionMetadata,
) -> str:
    if dimension == "unknown":
        return ""
    from app.advisor.orchestrator.industry_strategy import business_label

    label = business_label(meta)
    dim_name = dimension_label(dimension)
    wrong: list[str] = []
    if dimension != "growth":
        wrong.append("websites, SEO, social media, or lead generation")
    if dimension != "throughput":
        wrong.append("delivery delays, materials waits, or production bottlenecks")
    if dimension != "profitability":
        wrong.append("pricing, margins, or profit-per-hour analysis")
    if dimension != "efficiency":
        wrong.append("workflow waste or utilization")
    if dimension != "workforce":
        wrong.append("staff turnover, compensation, or career-path analysis")
    if dimension != "retention":
        wrong.append("churn or repeat-customer analysis")

    avoid = ", ".join(wrong[:3])
    return (
        f"\n\nPROBLEM DIMENSION LOCK: User is optimizing {dim_name} for {label}.\n"
        f"- Diagnose within this dimension ONLY — do NOT apply a different framework.\n"
        f"- Do NOT pivot to: {avoid}.\n"
        f"- Use hypotheses the user stated (pricing, efficiency, etc.) when present.\n"
        f"- Flow: metric clarity → hypothesis → validation → tradeoff → solution."
    )
