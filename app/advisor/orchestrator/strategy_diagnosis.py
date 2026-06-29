"""Strategic diagnosis layer — generic signals, insight before tactics."""

from __future__ import annotations

import re

from app.advisor.orchestrator.industry_strategy import (
    business_label,
    is_local_footprint,
    rag_industry_guidance_line,
)
from app.advisor.types import SessionMetadata

GrowthBlocker = str

_CHANNEL_SIGNALS: dict[str, tuple[str, ...]] = {
    "google_business": ("google business", "google profile", "gbp", "google listing"),
    "instagram": ("instagram",),
    "facebook": ("facebook",),
    "website": ("website", "web site"),
    "linkedin": ("linkedin",),
    "yelp": ("yelp",),
}

_UNDERPERFORMING_SIGNALS = (
    "already have",
    "we have",
    "neither seems",
    "neither ",
    "not bringing",
    "doesn't bring",
    "don't bring",
    "not working",
    "isn't working",
    "no new customers",
    "few new",
    "not many",
    "slowed down",
    "stalled",
)

_REFERRAL_SIGNALS = (
    "referral",
    "word of mouth",
    "word-of-mouth",
    "nearby",
    "live nearby",
    "local customers",
    "foot traffic",
)

_GROWTH_SIGNALS = (
    "grow",
    "growth",
    "stalled",
    "slowed",
    "new customers",
    "new members",
    "new clients",
    "awareness",
    "find us",
    "invest my time",
    "invest my money",
    "ways to grow",
    "invest",
)

_GROWTH_HYPOTHESIS_SIGNALS: dict[str, tuple[str, ...]] = {
    "pricing_sensitivity": ("pricing", "price", "too expensive", "cost", "sticker shock"),
    "onboarding_friction": ("onboarding", "setup", "getting started", "activation"),
    "product_complexity": ("complex", "confusing", "hard to use", "overwhelming"),
    "wrong_segment": ("wrong fit", "unqualified", "bad fit", "wrong customer"),
    "competition": ("competitor", "alternative", "switching"),
    "discovery": ("discover", "find us", "awareness", "visibility", "traffic"),
    "conversion": ("convert", "don't buy", "look but don't", "visit but don't"),
    "retention": ("churn", "returning less", "don't come back", "cancel"),
    "execution": ("not working", "underperform", "already have", "neither seems"),
}

_GROWTH_HYPOTHESIS_LABELS: dict[str, str] = {
    "pricing_sensitivity": "pricing sensitivity — cost or plan mismatch",
    "onboarding_friction": "onboarding friction — users don't reach value quickly",
    "product_complexity": "product complexity — setup or learning curve too steep",
    "wrong_segment": "wrong customer segment — poor-fit prospects",
    "competition": "increased competition — alternatives look better",
    "discovery": "discovery gap — not enough people find the business",
    "conversion": "conversion gap — interest doesn't become customers",
    "retention": "retention gap — customers don't return or renew",
    "execution": "channel execution — existing channels underperform",
}

_DIAGNOSTIC_BY_BLOCKER: dict[str, str] = {
    "discovery": (
        "How do new customers currently find {business} — and which of those channels "
        "drive more than referrals?"
    ),
    "conversion": (
        "When people discover {business} online or locally, what stops them from "
        "becoming a customer?"
    ),
    "retention": (
        "Is the main challenge attracting new customers, or keeping existing ones coming back?"
    ),
}


def detect_active_channels(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    blob = _blob(meta, message, history or [])
    found: list[str] = []
    for channel, signals in _CHANNEL_SIGNALS.items():
        if any(s in blob for s in signals):
            found.append(channel)
    return found


def channels_underperforming(message: str, history: list[str] | None = None) -> bool:
    blob = " ".join((history or []) + [message]).lower()
    return any(s in blob for s in _UNDERPERFORMING_SIGNALS)


def has_referral_traffic(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    blob = _blob(meta, message, history or [])
    return any(s in blob for s in _REFERRAL_SIGNALS)


def detect_growth_hypotheses(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return up to 5 growth-related (id, label) hypothesis pairs."""
    from app.advisor.orchestrator.diagnostic_trees import (
        default_hypotheses_for_framework,
        locate_funnel_stage,
    )
    from app.advisor.orchestrator.reasoning_engine import detect_business_model

    business_model = detect_business_model(meta, message, history)
    funnel = locate_funnel_stage(business_model, message, history)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    if funnel and funnel.hypotheses:
        for hid, label in funnel.hypotheses:
            if hid not in seen:
                seen.add(hid)
                found.append((hid, label))

    blob = _blob(meta, message, history or [])
    for category, signals in _GROWTH_HYPOTHESIS_SIGNALS.items():
        if any(s in blob for s in signals):
            if category not in seen:
                seen.add(category)
                found.append((category, _GROWTH_HYPOTHESIS_LABELS.get(category, category)))

    blocker = infer_growth_blocker(meta, message, history)
    if blocker != "unknown" and blocker not in seen:
        seen.add(blocker)
        found.append((blocker, _GROWTH_HYPOTHESIS_LABELS.get(blocker, blocker)))

    if len(found) < 3:
        defaults = default_hypotheses_for_framework(
            business_model if business_model != "unknown" else "local_retail"
        )
        for hid, label in defaults:
            if hid not in seen:
                seen.add(hid)
                found.append((hid, label))

    return found[:5]


def growth_diagnostic_question(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """Comparative question across top growth hypotheses."""
    from app.advisor.orchestrator.reasoning_engine import (
        detect_business_model,
        rank_hypotheses,
        select_differentiating_question,
    )

    pairs = detect_growth_hypotheses(meta, message, history)
    if not pairs:
        return diagnostic_question(meta, message, history)

    ranked = rank_hypotheses(pairs, message, history)
    framework = detect_business_model(meta, message, history)
    custom = select_differentiating_question(ranked, framework)
    if custom:
        return custom

    labels = [label.split("—")[0].strip() for _, label in pairs[:3]]
    label = business_label(meta)
    if len(labels) >= 3:
        return (
            f"To narrow this down for {label} — is it more about {labels[0]}, "
            f"{labels[1]}, or {labels[2]}?"
        )
    if len(labels) == 2:
        return f"For {label}, is it more about {labels[0]} or {labels[1]}?"
    return diagnostic_question(meta, message, history)


_OPS_PREEMPT_SIGNALS = (
    "delay",
    "delays",
    "backlog",
    "bottleneck",
    "compliance review",
    "account opening",
    "turnaround",
    "approval time",
    "waiting for approval",
    "move between",
    "handoff",
)


def _has_growth_signal(blob: str) -> bool:
    for kw in _GROWTH_SIGNALS:
        if kw in ("grow", "growth"):
            if re.search(rf"\b{re.escape(kw)}\b", blob):
                return True
        elif kw in blob:
            return True
    return False


def infer_growth_blocker(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> GrowthBlocker:
    if meta.growth_blocker in ("discovery", "conversion", "retention"):
        return meta.growth_blocker

    blob = _blob(meta, message, history or [])
    if any(kw in blob for kw in _OPS_PREEMPT_SIGNALS):
        return "unknown"
    if any(kw in blob for kw in ("returning less", "churn", "retention", "keep customers")):
        return "retention"
    if any(kw in blob for kw in ("visit but don't", "don't convert", "look but don't", "no foot traffic from")):
        return "conversion"
    if channels_underperforming(message, history) or _has_growth_signal(blob):
        return "discovery"
    return "unknown"


def _blob(meta: SessionMetadata, message: str, history: list[str]) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        message,
        " ".join(history),
    ]
    return " ".join(parts).lower()


def strategic_insight(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """Generic inference from signals — not per-industry templates."""
    blocker = infer_growth_blocker(meta, message, history)
    channels = detect_active_channels(meta, message, history)
    referrals = has_referral_traffic(meta, message, history)
    local = is_local_footprint(meta, message, history)
    label = business_label(meta)

    lines: list[str] = []

    if referrals and blocker in ("discovery", "unknown"):
        lines.append(
            "INFERENCE: Referrals or local traffic suggest existing customers are satisfied. "
            "The likely gap is discovery beyond the current network — not product quality."
        )
    elif blocker == "discovery":
        lines.append(
            "INFERENCE: The bottleneck appears to be discovery — not enough new people "
            "are finding the business."
        )
    elif blocker == "conversion":
        lines.append(
            "INFERENCE: People may be finding the business but not taking action — "
            "conversion, not awareness, may be the issue."
        )
    elif blocker == "retention":
        lines.append(
            "INFERENCE: The issue may be keeping customers, not attracting new ones."
        )

    if channels:
        names = ", ".join(c.replace("_", " ") for c in channels)
        if channels_underperforming(message, history):
            lines.append(
                f"CHANNELS IN PLACE ({names}) are underperforming — diagnose execution quality; "
                f"do NOT recommend setting them up again."
            )
        else:
            lines.append(f"Active channels mentioned: {names}.")

    if local and not channels:
        lines.append(
            f"Local footprint detected for {label} — prioritize channels where local "
            f"customers search (reviews, local search, community), not generic national tactics."
        )

    return " ".join(lines) if lines else ""


def diagnostic_question(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    blocker = infer_growth_blocker(meta, message, history)
    template = _DIAGNOSTIC_BY_BLOCKER.get(blocker, _DIAGNOSTIC_BY_BLOCKER["discovery"])
    return template.format(business=business_label(meta))


def should_insight_before_tactics(
    meta: SessionMetadata,
    message: str,
    history: list[str] | None = None,
) -> bool:
    """Business context + growth goal — insight before prescribing tactics."""
    if should_diagnose_before_recommend(meta, message, history):
        return True
    if not (meta.business_type or meta.industry):
        return False
    blob = _blob(meta, message, history or [])
    growth = any(kw in blob for kw in _GROWTH_SIGNALS)
    return has_referral_traffic(meta, message, history) and growth


def build_opening_value_block() -> str:
    return (
        "\n\nOPENING VALUE REQUIRED:\n"
        "User is unsure which growth channels matter (website, SEO, social, ads, AI).\n"
        "Give 2-3 sentences of education FIRST: channel fit depends on business model — "
        "local physical businesses vs online vs B2B professional services need different "
        "channels; AI tools rarely help until basics work.\n"
        "Then ask what type of business they run (ONE question). Do NOT pitch Boolmind."
    )


def should_diagnose_before_recommend(
    meta: SessionMetadata,
    message: str,
    history: list[str] | None = None,
) -> bool:
    """Existing channels reported as underperforming — diagnose before new tactics."""
    if meta.growth_blocker in ("discovery", "conversion", "retention"):
        return False
    channels = detect_active_channels(meta, message, history)
    if not channels:
        return False
    return channels_underperforming(message, history)


def build_diagnosis_block(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    from app.advisor.orchestrator.diagnostic_validation import no_solutions_clause
    from app.advisor.orchestrator.reasoning_engine import rank_hypotheses

    insight = strategic_insight(meta, message, history)
    diag_q = growth_diagnostic_question(meta, message, history)
    pairs = detect_growth_hypotheses(meta, message, history)
    ranked = rank_hypotheses(pairs, message, history)
    rag_line = rag_industry_guidance_line(meta)

    hypo_lines = [
        f"  - {h.label} (~{int(h.confidence * 100)}%)"
        for h in ranked[:5]
    ]
    hypo_block = "\n".join(hypo_lines) if hypo_lines else "  - discovery, conversion, retention (unconfirmed)"

    prescribe_note = ""
    if has_referral_traffic(meta, message, history) and not channels_underperforming(message, history):
        prescribe_note = (
            "7. Do NOT list generic tactics (GBP, Instagram, SEO) as prescriptions yet — "
            "state inference first, then ask the diagnostic question.\n"
        )

    return (
        f"\n\nSTRATEGIC DIAGNOSIS REQUIRED (before any tactics):\n"
        f"1. State your inference aloud (what's working vs what's not).\n"
        f"{insight}\n"
        f"2. List 3–5 plausible hypotheses (ranked, unconfirmed):\n"
        f"{hypo_block}\n"
        f"3. Do NOT recommend setting up channels the user already has.\n"
        f"4. Do NOT jump to generic SEO/social tips without explaining WHY for this business.\n"
        f"5. {rag_line}\n"
        f"6. {no_solutions_clause()}\n"
        f"7. End with ONE differentiating diagnostic question:\n"
        f"   \"{diag_q}\"\n"
        f"{prescribe_note}"
    )
