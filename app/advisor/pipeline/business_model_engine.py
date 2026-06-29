"""Business model inference — how the business makes money."""

from __future__ import annotations

import re

from app.advisor.pipeline.business_systems_models import (
    BusinessModelProfile,
    EconomicPriors,
    EvidenceStrength,
    IndustryHypothesis,
    PatternMatch,
)
from app.advisor.pipeline.discovery_models import FactGraph

_REVENUE_SIGNALS: dict[str, tuple[str, ...]] = {
    "subscription": ("subscription", "saas", "mrr", "arr", "recurring"),
    "commission": ("commission", "brokerage", "broker", "referral fee"),
    "unit_sales": ("unit", "product sales", "sku", "wholesale", "retail"),
    "AUM_fee": ("aum", "assets under management", "management fee"),
    "project_fee": ("project", "billable", "consulting", "engagement"),
    "marketplace_take_rate": ("marketplace", "take rate", "platform fee", "gmv"),
    "usage_based": ("usage", "consumption", "metered", "per seat"),
}

_COST_SIGNALS: dict[str, tuple[str, ...]] = {
    "COGS": ("cogs", "materials", "inventory cost", "cost of goods"),
    "labor_heavy": (
        "labor",
        "payroll",
        "staffing",
        "wage",
        "overtime",
        "compensation",
        "incentive",
        "clinician",
        "provider",
    ),
    "acquisition_cost": ("cac", "acquisition cost", "marketing spend"),
    "claims_payout": ("claims", "payout", "reimbursement"),
    "infrastructure": ("hosting", "infrastructure", "cloud cost"),
}

_PROPOSED_TOOL_PATTERN = re.compile(
    r"\b(?:considering|evaluating|exploring|looking at|planning to (?:buy|adopt|implement))\b",
    re.I,
)

_INDUSTRY_MARGIN_PRIORS: dict[str, float] = {
    "saas": 0.75,
    "software": 0.75,
    "healthcare": 0.55,
    "insurance": 0.5,
    "manufacturing": 0.45,
    "retail": 0.4,
    "consulting": 0.65,
    "logistics": 0.35,
}


def _full_blob(fact_graph: FactGraph, message: str = "") -> str:
    return f"{fact_graph.blob()} {message.lower()}".strip()


def infer_revenue_mechanisms(fact_graph: FactGraph, message: str = "") -> list[str]:
    blob = _full_blob(fact_graph, message)
    found: list[str] = []
    for mechanism, signals in _REVENUE_SIGNALS.items():
        for signal in signals:
            if signal not in blob:
                continue
            if mechanism in ("subscription", "usage_based") and signal == "software":
                if _PROPOSED_TOOL_PATTERN.search(blob):
                    continue
            found.append(mechanism)
            break
    if not found and re.search(
        r"\b(?:services? group|service business|professional services|clinic|practice)\b",
        blob,
        re.I,
    ):
        found.append("project_fee")
    return found


def infer_cost_structure(fact_graph: FactGraph, message: str = "") -> list[str]:
    blob = _full_blob(fact_graph, message)
    found: list[str] = []
    for cost_type, signals in _COST_SIGNALS.items():
        if any(s in blob for s in signals):
            found.append(cost_type)
    return found


def _scalability_profile(revenue: list[str], costs: list[str]) -> str:
    if "subscription" in revenue or "usage_based" in revenue:
        return "high_margin_low_marginal_cost"
    if "labor_heavy" in costs or "project_fee" in revenue:
        return "linear_labor"
    if "marketplace_take_rate" in revenue:
        return "network_effects_variable"
    if "unit_sales" in revenue:
        return "volume_dependent"
    return "unknown"


def _margin_sensitivity(revenue: list[str], costs: list[str], blob: str) -> list[str]:
    drivers: list[str] = []
    if "subscription" in revenue:
        drivers.extend(["cac", "onboarding_cost", "support_burden"])
    if "commission" in revenue:
        drivers.extend(["commission_compression", "claims_ratio"])
    if "marketplace_take_rate" in revenue:
        drivers.extend(["take_rate_pressure", "subsidy_burn"])
    if "unit_sales" in revenue:
        drivers.extend(["input_costs", "yield", "mix_shift"])
    if "project_fee" in revenue or "billable" in blob:
        drivers.extend(["utilization", "rate_card", "leverage"])
    if "pricing" in blob:
        drivers.append("pricing")
    if "forecast" in blob:
        drivers.append("forecasting")
    return list(dict.fromkeys(drivers))


def infer_business_model(
    fact_graph: FactGraph,
    pattern_matches: list[PatternMatch],
    *,
    message: str = "",
) -> BusinessModelProfile:
    revenue = infer_revenue_mechanisms(fact_graph, message)
    costs = infer_cost_structure(fact_graph, message)
    blob = _full_blob(fact_graph, message)
    fact_ids = [f.id for f in fact_graph.facts if f.category in ("context", "economic", "outcome")]

    confidence = 0.35
    strength: EvidenceStrength = "speculated"
    if revenue:
        confidence += 0.2 * len(revenue)
        strength = "inferred"
    if costs:
        confidence += 0.1 * len(costs)
    if pattern_matches:
        confidence += 0.1
    if len(fact_ids) >= 2:
        strength = "observed" if revenue and costs else "inferred"
    confidence = min(0.95, confidence)

    return BusinessModelProfile(
        revenue_mechanisms=revenue,
        cost_structure=costs,
        scalability_profile=_scalability_profile(revenue, costs),
        margin_sensitivity_drivers=_margin_sensitivity(revenue, costs, blob),
        confidence=round(confidence, 2),
        evidence_strength=strength,
        evidence_fact_ids=fact_ids[:8],
    )


def blended_economic_priors(
    business_model: BusinessModelProfile,
    industry_hypotheses: list[IndustryHypothesis],
) -> EconomicPriors:
    """80% business model / 20% industry — weak priors only."""
    model_margin = 0.5
    if business_model.margin_sensitivity_drivers:
        model_margin = min(0.9, 0.45 + 0.08 * len(business_model.margin_sensitivity_drivers))
    if "subscription" in business_model.revenue_mechanisms:
        model_margin = max(model_margin, 0.7)

    industry_margin = 0.5
    industry_weight_sum = 0.0
    for hyp in industry_hypotheses:
        if hyp.confidence < 0.5:
            continue
        prior = _INDUSTRY_MARGIN_PRIORS.get(hyp.label.lower(), 0.5)
        industry_margin += prior * hyp.confidence
        industry_weight_sum += hyp.confidence
    if industry_weight_sum > 0:
        industry_margin /= industry_weight_sum + 1

    blended = 0.8 * model_margin + 0.2 * industry_margin
    cash_w = 0.6 if "commission" in business_model.revenue_mechanisms else 0.5
    retention_w = 0.65 if "subscription" in business_model.revenue_mechanisms else 0.5

    return EconomicPriors(
        margin_sensitivity=round(blended, 3),
        cash_conversion_weight=round(cash_w, 3),
        retention_weight=round(retention_w, 3),
        model_confidence=business_model.confidence,
    )
