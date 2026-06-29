"""Workforce retention diagnosis — turnover, engagement, before interventions."""

from __future__ import annotations

from app.advisor.orchestrator.diagnostic_validation import (
    hypotheses_need_validation,
    no_solutions_clause,
)
from app.advisor.orchestrator.industry_strategy import business_label
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.types import SessionMetadata

WorkforceHypothesis = str

_WORKFORCE_HYPOTHESIS_SIGNALS: dict[str, tuple[str, ...]] = {
    "compensation": ("compensation", "pay", "salary", "wage", "underpaid", "not paid enough"),
    "workload": ("workload", "overwhelmed", "burnout", "peak period", "too many", "overworked"),
    "career_growth": (
        "career growth",
        "advancement",
        "promotion",
        "growth opportunity",
        "career path",
        "no path",
    ),
    "management": ("management", "manager", "leadership", "supervision", "support from"),
    "onboarding": ("recruiting", "training", "onboarding", "ramp up", "new hire"),
}

_HYPOTHESIS_LABELS: dict[str, str] = {
    "compensation": "compensation — pay not competitive or fair for the role",
    "workload": "workload — overwhelm during peak demand or understaffing",
    "career_growth": "career growth — limited advancement or development paths",
    "management": "management — leadership, support, or culture issues",
    "onboarding": "onboarding cost — constant recruiting and training churn",
}

_TRADEOFFS: dict[str, str] = {
    "compensation": (
        "If pay is the driver, career programs or perks won't stop departures — "
        "validate whether compensation is below market before investing elsewhere."
    ),
    "workload": (
        "If peak-period overwhelm drives turnover, mentorship or training adds more "
        "work — relief capacity or enrollment pacing may matter more than development programs."
    ),
    "career_growth": (
        "If advancement is the gap, raising pay alone won't retain people who see no "
        "future — but if workload is the real driver, promotion paths won't reduce burnout."
    ),
    "management": (
        "If management quality is the issue, compensation bumps are a short-term patch — "
        "but validate whether people leave managers or leave the work itself."
    ),
    "onboarding": (
        "High recruiting/training spend is a symptom — fixing onboarding alone without "
        "addressing why people leave just repeats the cycle."
    ),
}

_USER_FRAMED_HYPOTHESES: dict[str, tuple[str, ...]] = {
    "compensation": ("compensation", "pay", "salary"),
    "workload": ("workload", "overwhelmed"),
    "management": ("management", "manager"),
    "career_growth": ("career growth", "career", "advancement"),
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


def detect_workforce_hypotheses(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    blob = _blob(meta, message, history)
    found: list[str] = []
    for category, keywords in _USER_FRAMED_HYPOTHESES.items():
        if any(kw in blob for kw in keywords):
            found.append(category)
    if found:
        return list(dict.fromkeys(found))

    for category, signals in _WORKFORCE_HYPOTHESIS_SIGNALS.items():
        if any(s in blob for s in signals):
            found.append(category)
    return list(dict.fromkeys(found))


def hypothesis_unvalidated(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    hypotheses = detect_workforce_hypotheses(meta, message, history)
    return hypotheses_need_validation(
        hypotheses,
        message,
        history,
        meta.workforce_hypothesis,
        force_when_empty_keywords=(
            "turnover",
            "quit",
            "leaving",
            "recruiting",
            "instructor",
            "teacher",
            "employee",
        ),
    )


def infer_workforce_hypothesis(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> WorkforceHypothesis:
    if meta.workforce_hypothesis and meta.workforce_hypothesis not in ("unknown", "multiple"):
        return meta.workforce_hypothesis
    hypotheses = detect_workforce_hypotheses(meta, message, history)
    if len(hypotheses) > 1:
        return "multiple"
    if len(hypotheses) == 1:
        return hypotheses[0]
    return "unknown"


def workforce_strategic_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    blob = _blob(meta, message, history)
    lines: list[str] = []

    demand_ok = any(
        kw in blob
        for kw in (
            "enrollment",
            "increasing",
            "growing",
            "doing well",
            "more students",
            "more customers",
        )
    )
    turnover = any(
        kw in blob
        for kw in ("turnover", "quit", "leaving", "recruiting", "training time")
    )

    if demand_ok and turnover:
        lines.append(
            "INFERENCE: Demand/enrollment is healthy — the constraint is workforce "
            "stability and continuity, NOT customer acquisition."
        )
    elif turnover:
        lines.append(
            "INFERENCE: The core issue is why people leave and what it costs the "
            "business (recruiting, training, service continuity) — not growth tactics."
        )

    hypotheses = detect_workforce_hypotheses(meta, message, history)
    if hypotheses:
        labels = [_HYPOTHESIS_LABELS.get(h, h) for h in hypotheses]
        lines.append(
            f"HYPOTHESES (unconfirmed): turnover may stem from {', '.join(labels)}."
        )

    return " ".join(lines)


def strategic_tradeoff_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    hypotheses = detect_workforce_hypotheses(meta, message, history)
    if not hypotheses:
        return (
            "TRADEOFF: Fixing the wrong retention driver (e.g. pay raises when workload "
            "is the cause) is expensive and ineffective — validate what departing staff "
            "actually cite before launching programs."
        )
    if len(hypotheses) > 1:
        parts = [_TRADEOFFS.get(h, "") for h in hypotheses[:3]]
        return " ".join(p for p in parts if p)
    return _TRADEOFFS.get(hypotheses[0], _TRADEOFFS["workload"])


def workforce_diagnostic_question(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    hypotheses = detect_workforce_hypotheses(meta, message, history)
    label = business_label(meta)

    if len(hypotheses) >= 2:
        options = [_HYPOTHESIS_LABELS.get(h, h) for h in hypotheses[:3]]
        if len(options) == 2:
            return (
                f"When people leave {label}, is it more often because of "
                f"{options[0]}, or {options[1]}?"
            )
        return (
            f"When people leave {label}, is it more often because of "
            f"{options[0]}, {options[1]}, or {options[2]}?"
        )

    if len(hypotheses) == 1:
        others = [k for k in ("workload", "career_growth", "compensation") if k != hypotheses[0]][:2]
        opts = [_HYPOTHESIS_LABELS[hypotheses[0]]] + [_HYPOTHESIS_LABELS[k] for k in others]
        return (
            f"When people leave {label}, is it more often because of "
            f"{opts[0]}, {opts[1]}, or {opts[2]}?"
        )

    return (
        f"When staff leave {label}, is the main driver compensation, workload "
        f"during peak periods, limited career growth, or management?"
    )


def should_diagnose_workforce(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    dimension = detect_problem_dimension(meta, message, history)
    if dimension != "workforce":
        return False
    return hypothesis_unvalidated(meta, message, history)


def build_workforce_diagnosis_block(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.reasoning_engine import rank_hypotheses

    insight = workforce_strategic_insight(meta, message, history)
    tradeoff = strategic_tradeoff_insight(meta, message, history)
    diag_q = workforce_diagnostic_question(meta, message, history)
    ids = detect_workforce_hypotheses(meta, message, history)
    pairs = [(h, _HYPOTHESIS_LABELS.get(h, h)) for h in ids]
    ranked = rank_hypotheses(pairs, message, history)
    hypo_lines = "\n".join(
        f"  - {h.label} (~{int(h.confidence * 100)}%)" for h in ranked[:5]
    )

    return (
        f"\n\nWORKFORCE DIAGNOSIS REQUIRED (validate before any intervention):\n"
        f"Flow: Problem → Evidence → Hypothesis → Validation → Business Insight → Solution. "
        f"You are at VALIDATION — evidence is NOT confirmation.\n"
        f"1. Acknowledge what's working (e.g. rising enrollment) before the turnover gap.\n"
        f"{insight}\n"
        f"2. List 3–5 turnover hypotheses (ranked, unconfirmed):\n"
        f"{hypo_lines or '  - compensation, workload, career growth, management'}\n"
        f"3. STRATEGIC TRADEOFF — explain business implications aloud:\n"
        f"   {tradeoff}\n"
        f"4. {no_solutions_clause()}\n"
        f"5. Do NOT ask open-ended \"what do you think the reasons are\" — use a "
        f"comparative question with the user's stated hypotheses.\n"
        f"6. End with ONE comparative validation question:\n"
        f"   \"{diag_q}\"\n"
    )
