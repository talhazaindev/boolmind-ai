"""Domain-consistency validation — reject cross-industry terminology leakage."""

from __future__ import annotations

import re
from typing import Literal

from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

IndustryContext = Literal[
    "home_services",
    "healthcare",
    "financial_services",
    "logistics",
    "saas",
    "wholesale_distribution",
    "generic",
]

_INDUSTRY_SIGNALS: dict[IndustryContext, tuple[str, ...]] = {
    "home_services": (
        "hvac",
        "plumbing",
        "electrical",
        "field technician",
        "service location",
        "home services",
        "truck roll",
        "service call",
    ),
    "healthcare": (
        "dental",
        "clinic",
        "patient",
        "provider",
        "physician",
        "medical",
        "hospital",
        "healthcare",
    ),
    "financial_services": (
        "bank",
        "lending",
        "loan",
        "underwriting",
        "compliance review",
        "commercial lending",
        "account opening",
    ),
    "logistics": (
        "logistics",
        "shipment",
        "driver",
        "fleet",
        "delivery",
        "warehouse",
    ),
    "saas": (
        "saas",
        "arr",
        "b2b software",
        "subscription",
        "trial conversion",
        "crm",
        "mrr",
    ),
    "wholesale_distribution": (
        "wholesale",
        "distributor",
        "distribution center",
        "grocery chain",
        "restaurant supply",
        "food distribution",
    ),
}

_EXCLUSIVE_TERMS: dict[IndustryContext, tuple[str, ...]] = {
    "healthcare": (
        "chair utilization",
        "provider utilization",
        "claim denial",
        "reimbursement cycle",
    ),
    "home_services": (
        "technician utilization",
        "truck roll",
        "service call",
    ),
    "financial_services": (
        "underwriting queue",
        "loan application",
        "compliance queue",
    ),
    "logistics": (
        "driver wait",
        "shipment backlog",
    ),
    "saas": (
        "trial conversion",
        "mrr",
    ),
}

_METRIC_LABELS_BY_INDUSTRY: dict[IndustryContext, dict[str, str]] = {
    "generic": {
        "staffing_costs": "labor costs per location",
        "scheduling_inefficiency": "scheduling efficiency or capacity utilization",
        "labor_utilization": "utilization or billable hours",
        "pricing_gap": "pricing or average margin per job",
        "reimbursement_delay": "payment or reimbursement cycle times",
        "operating_expenses": "operating expenses",
    },
    "home_services": {
        "staffing_costs": "labor costs per location",
        "scheduling_inefficiency": "dispatch scheduling or route efficiency",
        "labor_utilization": "technician utilization or billable field hours",
        "pricing_gap": "pricing or average job margin",
        "operating_expenses": "operating expenses per location",
    },
    "healthcare": {
        "staffing_costs": "labor costs per location",
        "scheduling_inefficiency": "provider or chair utilization",
        "labor_utilization": "provider or chair utilization rates",
        "reimbursement_delay": "reimbursement cycle times or claim denial rates",
        "pricing_gap": "pricing or fee schedules",
    },
    "financial_services": {
        "staffing_costs": "labor costs per branch",
        "labor_utilization": "analyst utilization or processing capacity",
        "scheduling_inefficiency": "handoff delays between teams",
        "pricing_gap": "pricing or fee yield",
    },
    "logistics": {
        "staffing_costs": "labor costs per site",
        "labor_utilization": "driver or fleet utilization",
        "scheduling_inefficiency": "dispatch planning or route efficiency",
    },
    "saas": {
        "staffing_costs": "labor costs per team",
        "labor_utilization": "sales or delivery capacity utilization",
        "pricing_gap": "pricing or contract terms",
        "invoicing_delay": "time from closed-won to invoice sent",
        "collections_friction": "average days-to-pay",
    },
    "wholesale_distribution": {
        "pricing_competitiveness": "pricing competitiveness or average margin",
        "pricing_gap": "pricing competitiveness or average margin",
        "fulfillment_reliability": "on-time delivery rate or order fill accuracy",
        "service_response_time": "customer service response times",
        "account_management": "account management touchpoints",
        "staffing_costs": "warehouse labor costs per distribution center",
        "labor_utilization": "warehouse or fleet utilization",
    },
}


def conversation_blob(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        message,
        " ".join(history or []),
        " ".join(snapshot.confirmed_facts),
        snapshot.active_business_vertical or "",
    ]
    if graph:
        parts.extend(graph.pain_points)
        if graph.industry:
            parts.append(graph.industry)
    return " ".join(parts).lower()


def detect_industry_context(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> IndustryContext:
    blob = conversation_blob(meta, snapshot, message=message, history=history, graph=graph)
    vertical = (snapshot.active_business_vertical or meta.industry or "").lower()

    if vertical in ("financial_services", "banking"):
        return "financial_services"
    if vertical == "logistics":
        return "logistics"

    scores: dict[IndustryContext, int] = {k: 0 for k in _INDUSTRY_SIGNALS}
    for ctx, signals in _INDUSTRY_SIGNALS.items():
        for sig in signals:
            if len(sig) <= 5:
                if re.search(rf"\b{re.escape(sig)}\b", blob, re.I):
                    scores[ctx] += 1
            elif sig in blob:
                scores[ctx] += 1

    best = max(scores, key=lambda k: scores[k])
    if scores[best] >= 1:
        return best
    return "generic"


def metric_label_for_cause(
    cause_id: str,
    industry: IndustryContext,
    *,
    fallback: str | None = None,
) -> str:
    labels = _METRIC_LABELS_BY_INDUSTRY.get(industry) or {}
    generic = _METRIC_LABELS_BY_INDUSTRY["generic"]
    return labels.get(cause_id) or generic.get(cause_id) or fallback or cause_id.replace("_", " ")


def domain_terminology_violations(
    question: str,
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> list[str]:
    """Return violations when question uses another industry's vocabulary."""
    if not question.strip():
        return []
    active = detect_industry_context(
        meta, snapshot, message=message, history=history, graph=graph
    )
    q = question.lower()
    blob = conversation_blob(meta, snapshot, message=message, history=history, graph=graph)
    violations: list[str] = []

    for ctx, terms in _EXCLUSIVE_TERMS.items():
        if ctx == active:
            continue
        for term in terms:
            if term in q and term not in blob:
                violations.append(f"domain_terminology_mismatch:{term}")
    return violations


def sanitize_question_for_domain(
    question: str,
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str | None:
    """Replace contaminated metric labels with industry-appropriate phrasing."""
    violations = domain_terminology_violations(
        question, meta, snapshot, message=message, history=history, graph=graph
    )
    if not violations:
        return question

    industry = detect_industry_context(
        meta, snapshot, message=message, history=history, graph=graph
    )
    cleaned = question
    replacements = (
        ("billable or chair utilization rates", metric_label_for_cause("labor_utilization", industry)),
        ("provider or chair utilization", metric_label_for_cause("scheduling_inefficiency", industry)),
        ("chair utilization", metric_label_for_cause("labor_utilization", industry)),
        ("claim denial rates", metric_label_for_cause("reimbursement_delay", industry)),
        ("reimbursement cycle times", metric_label_for_cause("reimbursement_delay", industry)),
    )
    for old, new in replacements:
        lower = cleaned.lower()
        if old in lower:
            idx = lower.index(old)
            cleaned = cleaned[:idx] + new + cleaned[idx + len(old) :]

    if domain_terminology_violations(
        cleaned, meta, snapshot, message=message, history=history, graph=graph
    ):
        return None
    return cleaned
