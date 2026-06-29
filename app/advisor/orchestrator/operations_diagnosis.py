"""Operations/scaling diagnosis — validate hypotheses before solutions.

Generic signals only (delays, materials, capacity, approvals, planning).
No per-industry hardcoding.
"""

from __future__ import annotations

from app.advisor.orchestrator.diagnostic_validation import (
    hypotheses_need_validation,
    no_solutions_clause,
)
from app.advisor.orchestrator.industry_strategy import business_label
from app.advisor.types import SessionMetadata

OpsBottleneck = str

_BOTTLENECK_SIGNALS: dict[str, tuple[str, ...]] = {
    "materials": (
        "material",
        "materials",
        "supply",
        "supplies",
        "supplier",
        "procurement",
        "inventory",
        "stock",
    ),
    "approvals": (
        "approval",
        "approvals",
        "sign-off",
        "sign off",
        "client feedback",
        "revision",
        "revisions",
    ),
    "capacity": (
        "staffing",
        "hiring",
        "hire",
        "understaffed",
        "headcount",
        "keep up",
        "can't keep up",
        "cannot keep up",
        "production capacity",
        "capacity constraint",
    ),
    "scheduling": (
        "scheduling",
        "production planning",
        "project planning",
        "planning visibility",
        "planning gap",
        "workflow gap",
        "bottleneck",
        "bottlenecks",
        "backlog",
        "queue",
    ),
    "communication": (
        "visibility",
        "communication",
        "status update",
        "track progress",
        "don't know where",
        "dont know where",
    ),
}

_OPS_PROBLEM_SIGNALS = (
    "delay",
    "delayed",
    "delays",
    "stuck waiting",
    "get stuck",
    "stuck",
    "backlog",
    "backing up",
    "bottleneck",
    "keep up",
    "struggling",
    "frustrated",
    "behind schedule",
    "can't deliver",
    "cannot deliver",
    "production",
    "fulfillment",
    "orders",
)

_HYPOTHESIS_LABELS: dict[str, str] = {
    "materials": "waiting for materials or supplies",
    "approvals": "waiting for customer approvals or sign-offs",
    "capacity": "production capacity or staffing limits",
    "scheduling": "scheduling, planning, or workflow gaps",
    "communication": "communication or visibility breakdowns",
}

_TRADEOFF_INSIGHTS: dict[str, str] = {
    "materials": (
        "If work stalls waiting on materials, adding staff often raises costs "
        "without increasing output — fix supply/procurement or lead times first."
    ),
    "approvals": (
        "If approvals stall projects, more production capacity rarely shortens "
        "delivery — streamline decision cycles and revision loops first."
    ),
    "capacity": (
        "If the true constraint is capacity (not waiting on others), hiring or "
        "overtime may help — but only after ruling out material and approval waits."
    ),
    "scheduling": (
        "If some projects fly while others stall, the issue may be planning "
        "visibility rather than headcount — map where work piles up before adding resources."
    ),
    "communication": (
        "If teams lack visibility into project status, coordination breaks down "
        "even with enough staff — clarify handoffs before buying new tools."
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


def is_operations_problem(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    blob = _blob(meta, message, history)
    return any(sig in blob for sig in _OPS_PROBLEM_SIGNALS)


def detect_bottleneck_hypotheses(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    blob = _blob(meta, message, history)
    found: list[str] = []
    for category, signals in _BOTTLENECK_SIGNALS.items():
        if any(s in blob for s in signals):
            found.append(category)
    return found


def hypothesis_unvalidated(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    """True when root cause is not yet confirmed — stay in diagnose mode."""
    hypotheses = detect_bottleneck_hypotheses(meta, message, history)
    force = ()
    if is_operations_problem(meta, message, history):
        force = ("delay", "backlog", "bottleneck", "keep up")
    return hypotheses_need_validation(
        hypotheses,
        message,
        history,
        meta.ops_bottleneck,
        force_when_empty_keywords=force,
    )


def infer_ops_bottleneck(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> OpsBottleneck:
    if meta.ops_bottleneck and meta.ops_bottleneck not in ("unknown", "multiple"):
        return meta.ops_bottleneck

    hypotheses = detect_bottleneck_hypotheses(meta, message, history)
    if len(hypotheses) == 1:
        return hypotheses[0]
    if len(hypotheses) > 1:
        return "multiple"
    return "unknown"


def strategic_tradeoff_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """Generic tradeoff reasoning — why the wrong fix wastes money."""
    hypotheses = detect_bottleneck_hypotheses(meta, message, history)
    if not hypotheses:
        return (
            "TRADEOFF: Fixing the wrong bottleneck (e.g. hiring when materials are the "
            "constraint) increases cost without improving throughput — validate the "
            "dominant delay first."
        )
    if len(hypotheses) > 1:
        parts = [_TRADEOFF_INSIGHTS.get(h, "") for h in hypotheses[:3]]
        return " ".join(p for p in parts if p)
    return _TRADEOFF_INSIGHTS.get(hypotheses[0], _TRADEOFF_INSIGHTS["scheduling"])


def operations_strategic_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """What's working vs what's not — generic operations framing."""
    blob = _blob(meta, message, history)
    lines: list[str] = []

    if any(kw in blob for kw in ("demand", "increasing", "growing", "more orders")):
        lines.append(
            "INFERENCE: Demand appears strong — the challenge is execution and "
            "throughput, not lack of customers."
        )
    elif is_operations_problem(meta, message, history):
        lines.append(
            "INFERENCE: The challenge is operational — delivery, workflow, or "
            "capacity — not customer acquisition."
        )

    hypotheses = detect_bottleneck_hypotheses(meta, message, history)
    if hypotheses:
        labels = [_HYPOTHESIS_LABELS.get(h, h) for h in hypotheses]
        lines.append(
            f"HYPOTHESES (unconfirmed): delays may stem from {', '.join(labels)}."
        )

    return " ".join(lines)


def operations_diagnostic_question(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """Comparative question to validate which bottleneck dominates."""
    hypotheses = detect_bottleneck_hypotheses(meta, message, history)
    label = business_label(meta)

    if len(hypotheses) >= 2:
        options = [_HYPOTHESIS_LABELS.get(h, h) for h in hypotheses[:3]]
        if len(options) == 2:
            return (
                f"Which causes delays more often for {label}: "
                f"{options[0]}, or {options[1]}?"
            )
        return (
            f"Which causes delays more often for {label}: "
            f"{options[0]}, {options[1]}, or {options[2]}?"
        )

    if len(hypotheses) == 1:
        other = [k for k in _HYPOTHESIS_LABELS if k != hypotheses[0]][:2]
        opts = [_HYPOTHESIS_LABELS[hypotheses[0]]] + [_HYPOTHESIS_LABELS[o] for o in other]
        return (
            f"Which causes delays more often for {label}: "
            f"{opts[0]}, {opts[1]}, or {opts[2]}?"
        )

    return (
        f"Where do projects most often get stuck for {label} — "
        f"materials, approvals, production capacity, or planning?"
    )


def should_diagnose_operations(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    from app.advisor.orchestrator.problem_dimension import detect_problem_dimension

    dimension = detect_problem_dimension(meta, message, history)
    if dimension != "throughput":
        return False
    if not is_operations_problem(meta, message, history) and not (
        meta.business_type or meta.industry
    ):
        return False
    return hypothesis_unvalidated(meta, message, history)


def build_operations_diagnosis_block(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.reasoning_engine import rank_hypotheses

    insight = operations_strategic_insight(meta, message, history)
    tradeoff = strategic_tradeoff_insight(meta, message, history)
    diag_q = operations_diagnostic_question(meta, message, history)
    ids = detect_bottleneck_hypotheses(meta, message, history)
    pairs = [(h, _HYPOTHESIS_LABELS.get(h, h)) for h in ids]
    ranked = rank_hypotheses(pairs, message, history)
    hypo_lines = "\n".join(
        f"  - {h.label} (~{int(h.confidence * 100)}%)" for h in ranked[:5]
    )

    return (
        f"\n\nOPERATIONS DIAGNOSIS REQUIRED (validate before any solution):\n"
        f"Flow: Problem → Hypothesis → Validation → Insight → Solution. "
        f"You are at VALIDATION — do NOT skip to solutions.\n"
        f"1. Acknowledge what's working (e.g. strong demand) before what's broken.\n"
        f"{insight}\n"
        f"2. List 3–5 bottleneck hypotheses (ranked, unconfirmed):\n"
        f"{hypo_lines or '  - materials, approvals, capacity, scheduling'}\n"
        f"3. STRATEGIC TRADEOFF — explain aloud:\n"
        f"   {tradeoff}\n"
        f"4. {no_solutions_clause()}\n"
        f"5. End with ONE comparative diagnostic question:\n"
        f"   \"{diag_q}\"\n"
    )
