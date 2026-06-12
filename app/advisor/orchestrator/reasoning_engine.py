"""Central consulting reasoning — hypotheses, confidence, phases, prompt blocks."""

from __future__ import annotations

import re

from app.advisor.orchestrator.diagnostic_trees import (
    default_hypotheses_for_framework,
    differentiating_question,
    locate_funnel_stage,
)
from app.advisor.orchestrator.diagnostic_validation import no_solutions_clause
from app.advisor.orchestrator.industry_strategy import business_label
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.types import (
    EvidenceEntry,
    HypothesisState,
    ReasoningPhase,
    SessionMetadata,
)

_MIN_HYPOTHESES = 3
_MAX_HYPOTHESES = 5
_REJECT_THRESHOLD = 0.1
_CONFIRM_THRESHOLD = 0.55
_CONFIRM_GAP = 0.15

_BUSINESS_MODEL_SIGNALS: dict[str, tuple[str, ...]] = {
    "saas": (
        "saas",
        "software",
        "b2b software",
        "app",
        "platform",
        "trial",
        "activation",
        "mrr",
        "arr",
        "subscription software",
    ),
    "subscription": (
        "subscription",
        "subscriber",
        "recurring",
        "monthly plan",
        "membership",
        "cancel after",
    ),
    "service": (
        "agency",
        "consulting",
        "professional service",
        "client project",
        "billable",
        "service business",
    ),
    "education": (
        "school",
        "teacher",
        "instructor",
        "student",
        "enrollment",
        "learning center",
        "academy",
        "classroom",
    ),
    "local_retail": (
        "bakery",
        "restaurant",
        "retail",
        "store",
        "foot traffic",
        "local business",
        "shop",
    ),
}

_EVIDENCE_SUPPORT_PATTERNS: dict[str, tuple[str, ...]] = {
    "onboarding_friction": (
        "onboarding",
        "setup",
        "getting started",
        "don't complete",
        "stall",
        "drop off during",
    ),
    "pricing_sensitivity": (
        "pricing",
        "too expensive",
        "price",
        "cost",
        "sticker shock",
    ),
    "product_complexity": (
        "complex",
        "confusing",
        "hard to use",
        "steep learning",
        "overwhelming",
    ),
    "wrong_segment": (
        "wrong fit",
        "not our customer",
        "unqualified",
        "bad fit",
    ),
    "competition": (
        "competitor",
        "alternative",
        "switching",
        "other tool",
    ),
    "expectation_mismatch": (
        "expected",
        "promised",
        "not what",
        "disappointed",
    ),
    "delivery_issues": (
        "complaint",
        "support",
        "unresolved",
        "bug",
        "broken",
    ),
    "low_engagement": (
        "don't use",
        "inactive",
        "silent",
        "without interaction",
        "no engagement",
    ),
    "workload": (
        "overwhelmed",
        "peak period",
        "too much work",
        "burnout",
        "understaffed",
    ),
    "compensation": (
        "pay",
        "salary",
        "compensation",
        "underpaid",
    ),
    "career_growth": (
        "career",
        "advancement",
        "promotion",
        "growth opportunity",
    ),
    "management": (
        "management",
        "manager",
        "leadership",
    ),
    "pricing": (
        "pricing",
        "undercharg",
        "rates",
        "margin",
    ),
    "efficiency": (
        "efficiency",
        "wasted time",
        "manual",
        "busy work",
    ),
    "utilization": (
        "utilization",
        "low-margin",
        "client mix",
        "unprofitable",
    ),
    "capacity": (
        "capacity",
        "backlog",
        "can't keep up",
        "bottleneck",
    ),
    "discovery": (
        "don't find",
        "awareness",
        "discover",
        "visibility",
    ),
    "conversion": (
        "don't convert",
        "look but don't",
        "visit but don't",
    ),
    "retention": (
        "churn",
        "returning less",
        "don't come back",
    ),
}

_CONFIRMATION_PATTERNS = (
    r"the (main|primary|biggest) (issue|reason|cause|driver) is",
    r"(mostly|primarily|definitely) because",
    r"it's (definitely|mostly|primarily)",
    r"the root cause is",
    r"number one reason",
)


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


def detect_business_model(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    if meta.business_model and meta.business_model != "unknown":
        return meta.business_model
    blob = _blob(meta, message, history)
    scores: dict[str, int] = {}
    for model, signals in _BUSINESS_MODEL_SIGNALS.items():
        scores[model] = sum(1 for s in signals if s in blob)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best
    return "unknown"


def _detect_dimension_hypothesis_ids(
    meta: SessionMetadata,
    message: str,
    history: list[str] | None,
) -> list[tuple[str, str]]:
    """Delegate to dimension-specific detectors; return (id, label) pairs."""
    dimension = detect_problem_dimension(meta, message, history)

    if dimension == "workforce":
        from app.advisor.orchestrator.workforce_diagnosis import (
            _HYPOTHESIS_LABELS,
            detect_workforce_hypotheses,
        )

        ids = detect_workforce_hypotheses(meta, message, history)
        return [(h, _HYPOTHESIS_LABELS.get(h, h)) for h in ids]

    if dimension == "profitability":
        from app.advisor.orchestrator.profitability_diagnosis import (
            _HYPOTHESIS_LABELS,
            detect_profit_hypotheses,
        )

        ids = detect_profit_hypotheses(meta, message, history)
        return [(h, _HYPOTHESIS_LABELS.get(h, h)) for h in ids]

    if dimension == "throughput":
        from app.advisor.orchestrator.operations_diagnosis import (
            _HYPOTHESIS_LABELS,
            detect_bottleneck_hypotheses,
        )

        ids = detect_bottleneck_hypotheses(meta, message, history)
        return [(h, _HYPOTHESIS_LABELS.get(h, h)) for h in ids]

    if dimension in ("growth", "retention", "unknown"):
        from app.advisor.orchestrator.strategy_diagnosis import detect_growth_hypotheses

        return detect_growth_hypotheses(meta, message, history)

    return []


def generate_hypotheses(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Generate 3–5 plausible (id, label) hypotheses."""
    business_model = detect_business_model(meta, message, history)
    funnel = locate_funnel_stage(business_model, message, history)
    raw: list[tuple[str, str]] = []
    seen_ids: set[str] = set()

    if funnel and funnel.hypotheses:
        for hid, label in funnel.hypotheses:
            if hid not in seen_ids:
                seen_ids.add(hid)
                raw.append((hid, label))

    dimension_pairs = _detect_dimension_hypothesis_ids(meta, message, history)
    for hid, label in dimension_pairs:
        if hid not in seen_ids:
            seen_ids.add(hid)
            raw.append((hid, label))

    if len(raw) < _MIN_HYPOTHESES:
        defaults = default_hypotheses_for_framework(
            business_model if business_model != "unknown" else "local_retail"
        )
        for hid, label in defaults:
            if hid not in seen_ids:
                seen_ids.add(hid)
                raw.append((hid, label))

    return raw[:_MAX_HYPOTHESES]


def rank_hypotheses(
    pairs: list[tuple[str, str]],
    message: str = "",
    history: list[str] | None = None,
) -> list[HypothesisState]:
    """Assign initial confidence from signal strength."""
    if not pairs:
        return []

    blob = " ".join((history or []) + [message]).lower()
    scores: list[float] = []
    for hid, _ in pairs:
        patterns = _EVIDENCE_SUPPORT_PATTERNS.get(hid, ())
        score = 1.0 + sum(1.0 for p in patterns if p in blob)
        scores.append(score)

    total = sum(scores) or float(len(pairs))
    result: list[HypothesisState] = []
    for (hid, label), score in zip(pairs, scores):
        result.append(
            HypothesisState(
                id=hid,
                label=label,
                confidence=round(score / total, 3),
                status="active",
            )
        )
    result.sort(key=lambda h: h.confidence, reverse=True)
    return result


def _match_evidence_to_hypotheses(
    text: str,
    hypotheses: list[HypothesisState],
) -> tuple[list[str], list[str]]:
    blob = text.lower()
    supports: list[str] = []
    contradicts: list[str] = []
    for h in hypotheses:
        if h.status != "active":
            continue
        patterns = _EVIDENCE_SUPPORT_PATTERNS.get(h.id, ())
        if any(p in blob for p in patterns):
            supports.append(h.id)
    return supports, contradicts


def update_hypotheses_from_evidence(
    hypotheses: list[HypothesisState],
    message: str,
    history: list[str] | None,
    turn: int,
) -> tuple[list[HypothesisState], EvidenceEntry | None]:
    """Boost/contradict hypotheses from latest user message."""
    if not message.strip() or not hypotheses:
        return hypotheses, None

    supports, contradicts = _match_evidence_to_hypotheses(message, hypotheses)
    entry = EvidenceEntry(
        turn=turn,
        text=message[:300],
        supports=supports,
        contradicts=contradicts,
    )

    updated: list[HypothesisState] = []
    for h in hypotheses:
        new_h = h.model_copy(deep=True)
        if h.id in supports:
            new_h.confidence = min(1.0, h.confidence + 0.12)
            new_h.evidence_for.append(message[:120])
        elif supports and h.id not in supports and h.status == "active":
            new_h.confidence = max(0.0, h.confidence - 0.05)
        if new_h.confidence < _REJECT_THRESHOLD:
            new_h.status = "rejected"
        updated.append(new_h)

    active = [h for h in updated if h.status == "active"]
    if active:
        total = sum(h.confidence for h in active) or 1.0
        for h in active:
            h.confidence = round(h.confidence / total, 3)

    blob = message.lower()
    for pat in _CONFIRMATION_PATTERNS:
        if re.search(pat, blob):
            for h in active:
                if h.id in supports or (not supports and h == active[0]):
                    h.status = "confirmed"
                    h.confidence = 0.9
            break

    return updated, entry


def active_hypotheses(hypotheses: list[HypothesisState]) -> list[HypothesisState]:
    return [h for h in hypotheses if h.status == "active"]


def top_hypothesis(hypotheses: list[HypothesisState]) -> HypothesisState | None:
    active = active_hypotheses(hypotheses)
    return active[0] if active else None


def select_differentiating_question(
    hypotheses: list[HypothesisState],
    framework: str,
) -> str:
    active = active_hypotheses(hypotheses)
    if len(active) >= 2:
        custom = differentiating_question(framework, [active[0].id, active[1].id])
        if custom:
            return custom
        return (
            f"To narrow this down - is it more likely {active[0].label.split('—')[0].strip()}, "
            f"or {active[1].label.split('—')[0].strip()}?"
        )
    if len(active) == 1:
        return (
            f"What evidence would help confirm whether {active[0].label.split('—')[0].strip()} "
            f"is the main driver?"
        )
    return "What changed most recently that might explain this pattern?"


def should_converge(meta: SessionMetadata) -> bool:
    if meta.message_count < 3:
        return False
    turns_since = meta.message_count - meta.last_convergence_turn
    return turns_since >= 3 and turns_since <= 4


def _has_discovery_context(meta: SessionMetadata) -> bool:
    return bool(meta.business_type or meta.pain_point or meta.industry)


def _hypotheses_ranked(hypotheses: list[HypothesisState]) -> bool:
    active = active_hypotheses(hypotheses)
    return len(active) >= _MIN_HYPOTHESES


def _hypothesis_confirmed(hypotheses: list[HypothesisState]) -> bool:
    confirmed = [h for h in hypotheses if h.status == "confirmed"]
    if confirmed:
        return True
    active = active_hypotheses(hypotheses)
    if len(active) < 2:
        return bool(active)
    top = active[0]
    second = active[1]
    return top.confidence >= _CONFIRM_THRESHOLD and (top.confidence - second.confidence) >= _CONFIRM_GAP


def select_reasoning_phase(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> ReasoningPhase:
    """Advance through 7-phase consulting flow."""
    current = meta.reasoning_phase
    hypotheses = meta.hypotheses

    if not _has_discovery_context(meta):
        return "discovery"

    if current == "discovery":
        return "hypothesis_generation"

    if current == "hypothesis_generation":
        if _hypotheses_ranked(hypotheses):
            return "hypothesis_testing"
        return "hypothesis_generation"

    if current == "hypothesis_testing":
        evidence_turns = len(meta.evidence_log)
        if evidence_turns >= 1 or meta.message_count >= 4:
            return "convergence"
        return "hypothesis_testing"

    if current == "convergence":
        if _hypothesis_confirmed(hypotheses):
            return "strategic_insight"
        if meta.message_count - meta.last_convergence_turn >= 2:
            return "hypothesis_testing"
        return "convergence"

    if current == "strategic_insight":
        if meta.insight_delivered_turn > 0:
            return "solution_exploration"
        return "strategic_insight"

    if current == "solution_exploration":
        blob = _blob(meta, message, history)
        engaged = any(
            kw in blob
            for kw in ("which approach", "option", "sounds good", "tell me more", "how would")
        )
        if engaged or (meta.message_count >= 8 and _hypothesis_confirmed(hypotheses)):
            return "boolmind_positioning"
        return "solution_exploration"

    if current == "boolmind_positioning":
        return "boolmind_positioning"

    return current


def update_reasoning_state(
    meta: SessionMetadata,
    message: str,
    history: list[str] | None = None,
) -> SessionMetadata:
    """Update business model, funnel, hypotheses, evidence, and phase."""
    data = meta.model_copy(deep=True)
    business_model = detect_business_model(data, message, history)
    if business_model != "unknown":
        data.business_model = business_model

    funnel = locate_funnel_stage(business_model, message, history)
    if funnel:
        data.funnel_stage = funnel.stage

    pairs = generate_hypotheses(data, message, history)
    if pairs:
        if not data.hypotheses:
            data.hypotheses = rank_hypotheses(pairs, message, history)
        else:
            updated, entry = update_hypotheses_from_evidence(
                data.hypotheses, message, history, data.message_count
            )
            data.hypotheses = updated
            if entry and entry.supports:
                data.evidence_log = [*data.evidence_log, entry][-10:]

    phase = select_reasoning_phase(data, message, history)
    if phase == "convergence" and should_converge(data):
        data.last_convergence_turn = data.message_count
    data.reasoning_phase = phase
    return data


def build_hypothesis_block(hypotheses: list[HypothesisState], diag_question: str) -> str:
    active = active_hypotheses(hypotheses)
    if not active:
        return ""
    lines = [f"  - {h.label} (confidence ~{int(h.confidence * 100)}%)" for h in active[:5]]
    hypo_list = "\n".join(lines)
    return (
        f"\n\nHYPOTHESIS GENERATION REQUIRED:\n"
        f"List 3–5 plausible explanations aloud before asking your question:\n"
        f"{hypo_list}\n"
        f"Rank by relative likelihood — do NOT present as confirmed facts.\n"
        f"End with ONE differentiating question:\n"
        f"  \"{diag_question}\"\n"
        f"{no_solutions_clause()}"
    )


def build_hypothesis_test_block(
    hypotheses: list[HypothesisState],
    diag_question: str,
) -> str:
    active = active_hypotheses(hypotheses)
    testing = active[0].label if active else "the leading hypothesis"
    return (
        f"\n\nHYPOTHESIS TEST REQUIRED:\n"
        f"You are TESTING whether: {testing}\n"
        f"Purpose: eliminate possibilities — NOT gather random information.\n"
        f"State what you are testing, then ask:\n"
        f"  \"{diag_question}\"\n"
        f"{no_solutions_clause()}"
    )


def build_convergence_block(
    meta: SessionMetadata,
    hypotheses: list[HypothesisState],
) -> str:
    active = active_hypotheses(hypotheses)
    if len(active) < 2:
        return ""
    more_likely = active[:2]
    less_likely = active[-2:] if len(active) >= 4 else active[2:4]
    evidence_refs = [e.text[:80] for e in meta.evidence_log[-3:]]
    evidence_line = "; ".join(evidence_refs) if evidence_refs else "conversation so far"

    more_str = ", ".join(h.label.split("—")[0].strip() for h in more_likely)
    less_str = ", ".join(h.label.split("—")[0].strip() for h in less_likely) if less_likely else "other causes"

    return (
        f"\n\nCONVERGENCE REQUIRED:\n"
        f"Start with: \"Based on what we've learned...\"\n"
        f"More likely: {more_str}\n"
        f"Less likely: {less_str}\n"
        f"Reason: cite evidence — {evidence_line}\n"
        f"Use hedged language — do NOT claim certainty unless user confirmed.\n"
        f"End with at most ONE comparative question if a key gap remains."
    )


def build_insight_block(meta: SessionMetadata, hypotheses: list[HypothesisState]) -> str:
    top = top_hypothesis(hypotheses)
    label = business_label(meta)
    top_label = top.label.split("—")[0].strip() if top else "the leading cause"
    blob_hints = ""
    if meta.business_model == "education":
        blob_hints = (
            "If enrollment is growing while staff struggle, insight should note that growth "
            "may be outpacing operational support — hiring alone may not fix peak-period pressure."
        )
    return (
        f"\n\nSTRATEGIC INSIGHT REQUIRED:\n"
        f"Deliver business implication for {label} BEFORE any solution.\n"
        f"Leading cause (unconfirmed): {top_label}.\n"
        f"{blob_hints}\n"
        f"Add a NEW perspective — what this means for the business model.\n"
        f"Do NOT recommend programs, tools, hiring, or Boolmind yet.\n"
        f"No solution list — insight only."
    )


def build_solution_exploration_block(
    meta: SessionMetadata,
    hypotheses: list[HypothesisState],
) -> str:
    top = top_hypothesis(hypotheses)
    top_label = top.label.split("—")[0].strip() if top else "the confirmed constraint"
    return (
        f"\n\nSOLUTION EXPLORATION REQUIRED:\n"
        f"Addressing {top_label} — present 2–4 potential approaches with brief pros/cons.\n"
        f"Examples: product simplification, guided onboarding, customer success outreach, "
        f"trial redesign — pick what fits the business model.\n"
        f"Do NOT mention Boolmind yet.\n"
        f"End with: \"If you'd like, I can explore which of these fits your situation best.\""
    )


def build_boolmind_positioning_block(meta: SessionMetadata) -> str:
    label = business_label(meta)
    return (
        f"\n\nBOOLMIND POSITIONING (phase 7 only):\n"
        f"Summarize diagnosis for {label}, then explain where Boolmind could help implement "
        f"a solution — only after options were explored.\n"
        f"Frame as fit, not pitch: \"This is an area where Boolmind could help...\""
    )


def build_reasoning_prompt_blocks(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """Inject phase-appropriate reasoning blocks."""
    phase = meta.reasoning_phase
    framework = meta.business_model or "unknown"
    hypotheses = meta.hypotheses
    diag_q = select_differentiating_question(hypotheses, framework)

    if phase == "hypothesis_generation":
        return build_hypothesis_block(hypotheses, diag_q)
    if phase == "hypothesis_testing":
        return build_hypothesis_test_block(hypotheses, diag_q)
    if phase == "convergence" and should_converge(meta):
        return build_convergence_block(meta, hypotheses)
    if phase == "strategic_insight":
        return build_insight_block(meta, hypotheses)
    if phase == "solution_exploration":
        return build_solution_exploration_block(meta, hypotheses)
    if phase == "boolmind_positioning":
        return build_boolmind_positioning_block(meta)
    return ""


def mark_insight_delivered(meta: SessionMetadata) -> SessionMetadata:
    data = meta.model_copy(deep=True)
    data.insight_delivered_turn = data.message_count
    return data
