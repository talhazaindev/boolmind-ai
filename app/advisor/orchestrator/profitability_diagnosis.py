"""Profitability diagnosis — pricing, margins, utilization before solutions."""

from __future__ import annotations

from app.advisor.orchestrator.diagnostic_validation import (
    hypotheses_need_validation,
    no_solutions_clause,
)
from app.advisor.orchestrator.industry_strategy import business_label
from app.advisor.orchestrator.problem_dimension import (
    detect_problem_dimension,
    detect_user_stated_hypotheses,
)
from app.advisor.types import SessionMetadata

ProfitHypothesis = str

_PROFIT_HYPOTHESIS_SIGNALS: dict[str, tuple[str, ...]] = {
    "pricing": ("pricing", "price", "undercharg", "rates", "charge enough", "bill rate"),
    "utilization": (
        "low-margin",
        "low margin",
        "wrong clients",
        "client mix",
        "unprofitable events",
        "unprofitable projects",
    ),
    "scope_creep": ("scope creep", "unbilled", "extra work", "revisions", "out of scope"),
    "cost_structure": ("overhead", "costs rising", "expenses", "cost structure"),
    "efficiency": ("efficiency", "inefficien", "wasted time", "manual", "repetitive", "busy work"),
}

_HYPOTHESIS_LABELS: dict[str, str] = {
    "pricing": "pricing — not charging enough relative to effort",
    "efficiency": "efficiency — too much time on work that doesn't generate profit",
    "utilization": "client/event mix — too much low-margin work",
    "scope_creep": "scope creep — unbilled or out-of-scope work eating margin",
    "cost_structure": "cost structure — overhead rising faster than revenue",
    "staffing": "staffing — headcount without proportional profit",
}

_TRADEOFFS: dict[str, str] = {
    "pricing": (
        "If margins are thin because prices are too low, hiring or working harder "
        "only increases revenue at the same weak margin — fix pricing or packaging first."
    ),
    "efficiency": (
        "If the team is busy but profit is flat, the issue may be utilization — "
        "hours spent on admin, rework, or low-margin work — not lack of demand."
    ),
    "utilization": (
        "Taking on more events at low margins can make you busier and less profitable — "
        "validate which clients or event types actually contribute profit."
    ),
    "scope_creep": (
        "Scope creep turns profitable projects into loss-makers — adding staff won't "
        "fix margin erosion from unbilled work."
    ),
    "cost_structure": (
        "If overhead grew with headcount but profit didn't, the issue may be cost "
        "structure — not customer demand."
    ),
    "staffing": (
        "Adding capacity when margins are unvalidated can increase revenue without "
        "increasing profit — confirm unit economics first."
    ),
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


def detect_profit_hypotheses(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    """Prefer user-stated hypotheses; supplement with signal detection."""
    user_stated = detect_user_stated_hypotheses(meta, message, history)
    profit_relevant = [h for h in user_stated if h in _HYPOTHESIS_LABELS]
    if profit_relevant:
        return profit_relevant

    blob = _blob(meta, message, history)
    found: list[str] = []
    for category, signals in _PROFIT_HYPOTHESIS_SIGNALS.items():
        if any(s in blob for s in signals):
            found.append(category)
    return found


def hypothesis_unvalidated(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    hypotheses = detect_profit_hypotheses(meta, message, history)
    return hypotheses_need_validation(
        hypotheses,
        message,
        history,
        meta.profit_hypothesis,
        force_when_empty_keywords=("profit", "pricing", "margin", "overwhelmed"),
    )


def infer_profit_hypothesis(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> ProfitHypothesis:
    if meta.profit_hypothesis and meta.profit_hypothesis not in ("unknown", "multiple"):
        return meta.profit_hypothesis
    hypotheses = detect_profit_hypotheses(meta, message, history)
    if len(hypotheses) == 1:
        return hypotheses[0]
    if len(hypotheses) > 1:
        return "multiple"
    return "unknown"


def profitability_strategic_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    blob = _blob(meta, message, history)
    lines: list[str] = []

    demand_ok = any(
        kw in blob
        for kw in ("doing well", "strong demand", "business is good", "increasing demand", "busy")
    )
    profit_flat = any(
        kw in blob
        for kw in ("profit", "margin", "haven't increased", "hasn't increased", "not increased")
    )

    if demand_ok and profit_flat:
        lines.append(
            "INFERENCE: Demand appears healthy but profit is not scaling with activity — "
            "this is a profitability or utilization problem, NOT a customer-acquisition "
            "or delivery-throughput problem."
        )
    elif profit_flat:
        lines.append(
            "INFERENCE: The core question is unit economics — revenue per hour, per project, "
            "or per client — not whether you can find more customers."
        )

    hypotheses = detect_profit_hypotheses(meta, message, history)
    if hypotheses:
        labels = [_HYPOTHESIS_LABELS.get(h, h) for h in hypotheses]
        lines.append(
            f"HYPOTHESES (unconfirmed): profit gap may stem from {', '.join(labels)}."
        )

    return " ".join(lines)


def strategic_tradeoff_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    hypotheses = detect_profit_hypotheses(meta, message, history)
    if not hypotheses:
        return (
            "TRADEOFF: Being busy without rising profit usually means margin or utilization "
            "is the constraint — adding capacity or marketing spend can make the problem worse."
        )
    if len(hypotheses) > 1:
        parts = [_TRADEOFFS.get(h, "") for h in hypotheses[:3]]
        return " ".join(p for p in parts if p)
    return _TRADEOFFS.get(hypotheses[0], _TRADEOFFS["efficiency"])


def profitability_diagnostic_question(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    from app.advisor.pipeline.hypothesis_engine import build_hypothesis_evidence_question
    from app.advisor.pipeline.question_value import build_profitability_evidence_question
    from app.advisor.types import HypothesisSnapshot

    evidence_q = build_hypothesis_evidence_question(
        meta,
        HypothesisSnapshot(),
        message=message,
        history=history,
    )
    if evidence_q:
        return evidence_q

    evidence_q = build_profitability_evidence_question(
        meta,
        HypothesisSnapshot(),
        message=message,
        history=history,
    )
    if evidence_q:
        return evidence_q

    label = business_label(meta)
    return (
        f"For {label}, which operational factor shifted most recently in a way "
        f"that could explain what you described?"
    )


def should_diagnose_profitability(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    dimension = detect_problem_dimension(meta, message, history)
    if dimension != "profitability":
        return False
    return hypothesis_unvalidated(meta, message, history)


def build_profitability_diagnosis_block(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.reasoning_engine import rank_hypotheses

    insight = profitability_strategic_insight(meta, message, history)
    tradeoff = strategic_tradeoff_insight(meta, message, history)
    diag_q = profitability_diagnostic_question(meta, message, history)
    ids = detect_profit_hypotheses(meta, message, history)
    pairs = [(h, _HYPOTHESIS_LABELS.get(h, h)) for h in ids]
    ranked = rank_hypotheses(pairs, message, history)
    hypo_lines = "\n".join(
        f"  - {h.label} (~{int(h.confidence * 100)}%)" for h in ranked[:5]
    )

    return (
        f"\n\nPROFITABILITY DIAGNOSIS REQUIRED (validate before any solution):\n"
        f"Flow: Metric (profit) → Hypothesis → Validation → Tradeoff → Solution. "
        f"You are at VALIDATION — do NOT skip to solutions.\n"
        f"1. Acknowledge what's working (e.g. strong demand) before the profit gap.\n"
        f"{insight}\n"
        f"2. List 3–5 profit hypotheses (ranked, unconfirmed):\n"
        f"{hypo_lines or '  - pricing, efficiency, utilization, scope creep'}\n"
        f"3. STRATEGIC TRADEOFF — explain aloud:\n"
        f"   {tradeoff}\n"
        f"4. Do NOT discuss delivery delays, materials, production bottlenecks, or hiring "
        f"unless the user raised throughput — this is a profitability question.\n"
        f"5. {no_solutions_clause()}\n"
        f"6. End with ONE comparative diagnostic question using the user's own framing "
        f"(pricing vs efficiency vs mix):\n"
        f"   \"{diag_q}\"\n"
    )
