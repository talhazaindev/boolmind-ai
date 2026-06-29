"""Domain-specific diagnostic funnels — locate failure points before hypotheses."""

from __future__ import annotations

import re

from typing import Final, NamedTuple

FRAMEWORKS: dict[str, list[str]] = {
    "saas": [
        "lead_gen",
        "qualification",
        "demo",
        "trial",
        "activation",
        "conversion",
        "retention",
    ],
    "subscription": [
        "acquisition",
        "onboarding",
        "first_value",
        "retention",
        "expansion",
    ],
    "service": [
        "lead_flow",
        "sales",
        "delivery",
        "capacity",
        "profitability",
    ],
    "education": [
        "enrollment",
        "teacher_capacity",
        "student_satisfaction",
        "retention",
        "growth",
    ],
    "local_retail": [
        "awareness",
        "foot_traffic",
        "conversion",
        "repeat",
        "referral",
    ],
}

_STAGE_SIGNALS: dict[str, dict[str, tuple[str, ...]]] = {
    "saas": {
        "lead_gen": ("lead gen", "leads", "top of funnel", "traffic", "visitors"),
        "qualification": ("qualification", "qualified lead", "mql", "sql"),
        "demo": ("demo", "sales call", "discovery call", "book a call"),
        "trial": ("trial", "free trial", "signup", "sign up", "sign-up"),
        "activation": ("activation", "activated", "first use", "onboarding complete", "aha moment"),
        "conversion": (
            "trial conversion",
            "convert",
            "conversion rate",
            "paid",
            "upgrade",
            "purchase",
        ),
        "retention": ("churn", "cancel", "retention", "renewal", "downgrade"),
    },
    "subscription": {
        "acquisition": ("acquisition", "new subscriber", "new customer", "signup"),
        "onboarding": ("onboarding", "setup", "getting started", "first week"),
        "first_value": ("first value", "time to value", "first success", "week 1", "week 2"),
        "retention": ("churn", "cancel", "retention", "renewal", "after week"),
        "expansion": ("upsell", "expansion", "upgrade", "add seats"),
    },
    "service": {
        "lead_flow": ("lead", "inquiry", "referral", "pipeline"),
        "sales": ("close rate", "proposal", "quote", "sales"),
        "delivery": ("delivery", "fulfillment", "project", "turnaround"),
        "capacity": ("capacity", "backlog", "bandwidth", "overwhelmed"),
        "profitability": ("margin", "profit", "pricing", "utilization"),
    },
    "education": {
        "enrollment": ("enrollment", "enroll", "students", "sign up", "registration"),
        "teacher_capacity": (
            "teacher",
            "instructor",
            "staff",
            "turnover",
            "recruiting",
            "training",
        ),
        "student_satisfaction": (
            "complain",
            "satisfaction",
            "overwhelmed",
            "quality",
            "feedback",
        ),
        "retention": ("retention", "drop out", "churn", "leave", "cancel"),
        "growth": ("grow", "growth", "expand", "more students"),
    },
    "local_retail": {
        "awareness": ("discover", "find us", "awareness", "visibility"),
        "foot_traffic": ("foot traffic", "walk-in", "visits", "store traffic"),
        "conversion": ("convert", "purchase", "buy", "checkout"),
        "repeat": ("repeat", "returning", "loyalty"),
        "referral": ("referral", "word of mouth", "recommend"),
    },
}

_STAGE_HYPOTHESES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "saas": {
        "conversion": [
            ("pricing_sensitivity", "pricing sensitivity — sticker shock or plan mismatch"),
            ("onboarding_friction", "onboarding friction — users don't reach value"),
            ("product_complexity", "product complexity — setup or learning curve too steep"),
            ("wrong_segment", "wrong customer segment — trials from poor-fit prospects"),
            ("competition", "increased competition — alternatives look better"),
        ],
        "activation": [
            ("onboarding_friction", "onboarding friction — users stall before first value"),
            ("product_complexity", "product complexity — too many steps to activate"),
            ("expectation_mismatch", "expectation mismatch — trial doesn't match promise"),
            ("missing_guidance", "missing guidance — no guided workflow or success path"),
            ("technical_issues", "technical issues — bugs or integration blockers"),
        ],
        "retention": [
            ("expectation_mismatch", "expectation mismatch — product doesn't deliver promised value"),
            ("delivery_issues", "delivery or support issues — unresolved problems"),
            ("pricing_concerns", "pricing concerns — value doesn't justify cost"),
            ("competition", "competition — users switch to alternatives"),
            ("low_engagement", "low engagement — users never formed a habit"),
        ],
        "trial": [
            ("onboarding_friction", "onboarding friction — users don't complete setup"),
            ("pricing_sensitivity", "pricing sensitivity — cost visible too early"),
            ("wrong_segment", "wrong segment — unqualified trials"),
            ("product_complexity", "product complexity — trial feels overwhelming"),
            ("competition", "competition — evaluating multiple tools"),
        ],
    },
    "subscription": {
        "retention": [
            ("expectation_mismatch", "expectation mismatch — value gap after signup"),
            ("onboarding_gap", "onboarding gap — users never reach first value"),
            ("pricing_concerns", "pricing concerns — renewal feels too expensive"),
            ("delivery_issues", "delivery or support issues"),
            ("low_engagement", "low engagement — usage drops after week 2"),
        ],
        "onboarding": [
            ("onboarding_friction", "onboarding friction — setup too complex"),
            ("missing_guidance", "missing guidance — no clear success path"),
            ("expectation_mismatch", "expectation mismatch — product harder than expected"),
            ("technical_issues", "technical issues — setup failures"),
            ("wrong_segment", "wrong segment — poor-fit subscribers"),
        ],
        "first_value": [
            ("expectation_mismatch", "expectation mismatch — promised value not felt"),
            ("onboarding_friction", "onboarding friction — too long to first win"),
            ("product_complexity", "product complexity — features hard to use"),
            ("delivery_issues", "delivery issues — support gaps during ramp"),
            ("low_engagement", "low engagement — no habit formed by week 2"),
        ],
    },
    "service": {
        "delivery": [
            ("capacity", "capacity — team can't keep up with demand"),
            ("scope_creep", "scope creep — projects expand without margin"),
            ("process_gaps", "process gaps — handoffs and approvals slow delivery"),
            ("quality_issues", "quality issues — rework eats margin"),
            ("wrong_clients", "wrong clients — low-margin work dominates"),
        ],
        "capacity": [
            ("hiring_gap", "hiring gap — headcount can't match demand"),
            ("utilization", "utilization — skilled time spent on low-value work"),
            ("process_gaps", "process gaps — inefficiency in workflow"),
            ("scope_creep", "scope creep — unbilled work"),
            ("scheduling", "scheduling — poor planning creates bottlenecks"),
        ],
    },
    "education": {
        "teacher_capacity": [
            ("workload", "workload — teachers overwhelmed during peak enrollment"),
            ("compensation", "compensation — pay not competitive"),
            ("career_growth", "career growth — limited advancement paths"),
            ("management", "management — leadership or support issues"),
            ("onboarding_cost", "onboarding cost — constant recruiting and training churn"),
        ],
        "enrollment": [
            ("awareness", "awareness — not enough families find the program"),
            ("conversion", "conversion — inquiries don't enroll"),
            ("capacity", "capacity — can't accept more students"),
            ("reputation", "reputation — reviews or word-of-mouth weak"),
            ("pricing", "pricing — cost barrier for target families"),
        ],
    },
}

_DIFFERENTIATING_QUESTIONS: dict[str, dict[str, str]] = {
    "saas": {
        "onboarding_friction|pricing_sensitivity": (
            "Where do prospects typically disengage — during onboarding, "
            "after pricing discussions, or later in the trial?"
        ),
        "expectation_mismatch|delivery_issues": (
            "Do cancellations tend to follow complaints, or do customers "
            "leave without significant interaction?"
        ),
        "product_complexity|onboarding_friction": (
            "Is the drop-off more about too many setup steps, or users "
            "not understanding what to do first?"
        ),
    },
    "subscription": {
        "expectation_mismatch|low_engagement": (
            "Do cancellations tend to follow complaints, or do customers "
            "leave without significant interaction?"
        ),
        "onboarding_gap|pricing_concerns": (
            "Where do subscribers disengage — during onboarding, "
            "after pricing discussions, or later in usage?"
        ),
    },
    "education": {
        "workload|compensation": (
            "When staff leave, is it more often because of workload during "
            "peak periods, compensation, or limited career growth?"
        ),
        "workload|career_growth": (
            "When teachers leave, is it more about peak-period overwhelm "
            "or limited advancement opportunities?"
        ),
    },
}


class FunnelLocation(NamedTuple):
    framework: str
    stage: str
    hypotheses: list[tuple[str, str]]


def locate_funnel_stage(
    framework: str,
    message: str,
    history: list[str] | None = None,
) -> FunnelLocation | None:
    """Map conversation signals to a funnel stage and default hypotheses."""
    blob = " ".join((history or []) + [message]).lower()
    stages = FRAMEWORKS.get(framework, [])
    if not stages:
        return None

    best_stage = ""
    best_score = 0
    for stage in stages:
        signals = _STAGE_SIGNALS.get(framework, {}).get(stage, ())
        score = sum(1 for s in signals if s in blob)
        if score > best_score:
            best_score = score
            best_stage = stage

    if not best_stage:
        return None

    hypotheses = _STAGE_HYPOTHESES.get(framework, {}).get(best_stage, [])
    return FunnelLocation(framework=framework, stage=best_stage, hypotheses=list(hypotheses))


def default_hypotheses_for_framework(framework: str) -> list[tuple[str, str]]:
    """Fallback hypotheses when stage is unknown."""
    defaults: dict[str, list[tuple[str, str]]] = {
        "saas": _STAGE_HYPOTHESES["saas"]["conversion"],
        "subscription": _STAGE_HYPOTHESES["subscription"]["retention"],
        "service": _STAGE_HYPOTHESES["service"]["delivery"],
        "education": _STAGE_HYPOTHESES["education"]["teacher_capacity"],
        "local_retail": [
            ("discovery", "discovery — not enough people find the business"),
            ("conversion", "conversion — visitors don't become customers"),
            ("retention", "retention — customers don't return"),
            ("execution", "channel execution — existing channels underperform"),
            ("competition", "competition — alternatives draw customers away"),
        ],
    }
    return list(defaults.get(framework, defaults["local_retail"]))


def differentiating_question(
    framework: str,
    hypothesis_ids: list[str],
) -> str | None:
    """Return a question that splits the top two hypotheses."""
    questions = _DIFFERENTIATING_QUESTIONS.get(framework, {})
    if len(hypothesis_ids) < 2:
        return None
    key = f"{hypothesis_ids[0]}|{hypothesis_ids[1]}"
    if key in questions:
        return questions[key]
    key_rev = f"{hypothesis_ids[1]}|{hypothesis_ids[0]}"
    return questions.get(key_rev)


# --- Universal workflow model (industry-agnostic ops) ---

UNIVERSAL_STAGES: Final[tuple[str, ...]] = (
    "intake",
    "preparation",
    "execution",
    "quality_gate",
    "delivery",
    "exception_loop",
)

_UNIVERSAL_STAGE_SIGNALS: Final[dict[str, tuple[str, ...]]] = {
    "intake": (
        "intake", "application received", "order received", "signup", "lead",
        "trial", "request submitted",
    ),
    "preparation": (
        "gather document", "verify", "plan route", "assign driver", "onboarding",
        "setup", "spreadsheet", "data entry", "collect",
    ),
    "execution": (
        "underwriting", "analysis", "dispatch", "processing", "transit",
        "analyst", "production", "fulfillment",
    ),
    "quality_gate": (
        "compliance", "review queue", "qc", "inspection", "audit",
        "approval team", "manual review",
    ),
    "delivery": (
        "approval decision", "customer delivery", "value realized",
        "close", "ship complete",
    ),
    "exception_loop": (
        "exception", "rework", "went back", "missing doc", "revert",
        "manual intervention", "edge case",
    ),
}

_OPS_HYPOTHESES: Final[dict[str, tuple[str, str]]] = {
    "queue_saturation": "queue saturation — volume exceeds review capacity",
    "exception_handling_gap": "exception handling gap — automation misses edge cases",
    "manual_handoff": "manual handoff — teams coordinate outside systems",
    "capacity_ceiling": "capacity ceiling — headcount cannot match volume",
    "data_reentry": "data re-entry — same facts entered in multiple systems",
    "prioritization_gap": "prioritization gap — no rules for queue ordering",
    "ocr_accuracy": "extraction accuracy — standard documents misread",
}

_OPS_DIFFERENTIATING: Final[dict[str, str]] = {
    "queue_saturation|exception_handling_gap": (
        "Is the delay mostly queue volume waiting for review, or rework caused by "
        "exceptions that automation missed?"
    ),
    "exception_handling_gap|ocr_accuracy": (
        "When automation failed, was it mostly unusual document types, or standard "
        "statements the system misread?"
    ),
    "queue_saturation|prioritization_gap": (
        "Is the backlog growing because review capacity is too low, or because "
        "applications aren't being prioritized effectively?"
    ),
    "manual_handoff|capacity_ceiling": (
        "Is the bottleneck more about too many manual handoffs between teams, "
        "or simply not enough people at the critical step?"
    ),
    "manual_handoff|prioritization_gap": (
        "Is the delay mostly from handoffs between teams, or from unclear rules "
        "about which applications get reviewed first?"
    ),
    "prioritization_gap|manual_handoff": (
        "Is the delay mostly from handoffs between teams, or from unclear rules "
        "about which applications get reviewed first?"
    ),
    "capacity_ceiling|data_reentry": (
        "Are analysts slowed down by sheer volume, or by re-entering the same "
        "data into multiple systems?"
    ),
}


def _term_in_blob(term: str, text: str) -> bool:
    if len(term) <= 5:
        return bool(re.search(rf"\b{re.escape(term)}\b", text, re.I))
    return term in text


def locate_universal_stage(
    graph: object,
    blob: str,
) -> str:
    """Map conversation to universal workflow stage."""
    text = blob.lower()
    if hasattr(graph, "workflow_stages"):
        stages = getattr(graph, "workflow_stages", {})
        if stages.get("quality_gate") and stages["quality_gate"].confidence >= 0.7:
            return "quality_gate"
        if stages.get("exception_loop") and stages["exception_loop"].confidence >= 0.7:
            return "exception_loop"
    best = "unknown"
    best_score = 0
    for stage in UNIVERSAL_STAGES:
        signals = _UNIVERSAL_STAGE_SIGNALS.get(stage, ())
        score = sum(1 for s in signals if _term_in_blob(s, text))
        if score > best_score:
            best_score = score
            best = stage
    return best if best_score >= 2 else "unknown"


def rank_ops_hypotheses(
    graph: object,
    snapshot: object,
) -> list[tuple[str, str, float]]:
    """Return (id, label, confidence) for ops throughput hypotheses."""
    blob = ""
    if hasattr(graph, "pain_points"):
        blob += " ".join(getattr(graph, "pain_points", []))
    if hasattr(graph, "metrics"):
        blob += " " + " ".join(getattr(graph, "metrics", {}).keys())
    if hasattr(snapshot, "confirmed_facts"):
        blob += " " + " ".join(getattr(snapshot, "confirmed_facts", []))
    blob = blob.lower()

    scores: dict[str, float] = {}
    if "backlog" in blob or "queue" in blob:
        scores["queue_saturation"] = 0.72
    if any(p in blob for p in ("exception", "went back", "poor adoption")):
        scores["exception_handling_gap"] = 0.68
    if "manual" in blob and ("handoff" in blob or "email" in blob or "team" in blob):
        scores["manual_handoff"] = 0.65
    if "analyst" in blob or "coordinator" in blob:
        scores["capacity_ceiling"] = 0.6
    if "enter data" in blob or "re-enter" in blob or "origination system" in blob:
        scores["data_reentry"] = 0.58
    if "compliance" in blob and "priorit" in blob:
        scores["prioritization_gap"] = 0.7
    if "compliance" in blob and any(
        p in blob for p in ("risk team", "move between", "handoff", "analysts", "teams")
    ):
        scores["manual_handoff"] = max(scores.get("manual_handoff", 0.0), 0.58)
    if "compliance" in blob and any(p in blob for p in ("hours", "days", "review")):
        scores["prioritization_gap"] = max(scores.get("prioritization_gap", 0.0), 0.49)
    if hasattr(snapshot, "confidence_scores"):
        for hid, conf in getattr(snapshot, "confidence_scores", {}).items():
            if hid in _OPS_HYPOTHESES:
                scores[hid] = max(scores.get(hid, 0.0), conf)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        (hid, _OPS_HYPOTHESES[hid], conf)
        for hid, conf in ranked
        if hid in _OPS_HYPOTHESES
    ]


def ops_differentiating_question(hypothesis_ids: list[str]) -> str | None:
    if len(hypothesis_ids) < 2:
        return None
    key = f"{hypothesis_ids[0]}|{hypothesis_ids[1]}"
    if key in _OPS_DIFFERENTIATING:
        return _OPS_DIFFERENTIATING[key]
    key_rev = f"{hypothesis_ids[1]}|{hypothesis_ids[0]}"
    return _OPS_DIFFERENTIATING.get(key_rev)

