"""Economic driver detection — model and weak industry priors."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessDriver,
    BusinessImpactScore,
    BusinessModelProfile,
    EconomicPriors,
    ImpactWeights,
)
from app.advisor.pipeline.discovery_models import FactGraph

_DRIVER_SIGNALS: dict[BusinessDriver, tuple[str, ...]] = {
    "revenue_growth": ("revenue", "growing", "growth", "sales up"),
    "gross_margin": ("margin", "profitability", "profit", "cogs"),
    "retention": ("retention", "churn", "renewal", "leaving"),
    "cash_conversion": ("cash", "collections", "invoice", "payment", "dso"),
    "capacity_utilization": ("utilization", "capacity", "backlog", "overtime"),
    "customer_acquisition": ("acquisition", "cac", "leads", "pipeline"),
    "risk_exposure": ("risk", "compliance", "audit", "regulatory"),
    "working_capital": ("working capital", "inventory", "payables", "receivable"),
}


def detect_driver_signals(
    fact_graph: FactGraph,
    priors: EconomicPriors,
    message: str = "",
) -> list[BusinessDriver]:
    blob = f"{fact_graph.blob()} {message.lower()}"
    drivers: list[BusinessDriver] = []
    for driver, signals in _DRIVER_SIGNALS.items():
        if any(s in blob for s in signals):
            drivers.append(driver)
    if priors.retention_weight > 0.6 and "retention" not in [d for d in drivers]:
        if "subscription" in blob or "churn" in blob:
            drivers.append("retention")
    if priors.cash_conversion_weight > 0.55 and "cash" in blob:
        if "cash_conversion" not in drivers:
            drivers.append("cash_conversion")
    return list(dict.fromkeys(drivers))


def revenue_cash_divergence(fact_graph: FactGraph, message: str = "") -> bool:
    blob = f"{fact_graph.blob()} {message.lower()}"
    rev_up = any(s in blob for s in ("revenue growing", "revenue up", "sales growing", "revenue is growing"))
    cash_bad = any(s in blob for s in ("cash unstable", "cash flow", "collections", "invoice", "unstable"))
    return rev_up and cash_bad


def margin_pressure_analysis(
    fact_graph: FactGraph,
    business_model: BusinessModelProfile,
    priors: EconomicPriors,
) -> list[str]:
    blob = fact_graph.blob()
    pressures: list[str] = []
    if "margin" in blob or "profit" in blob:
        pressures.extend(business_model.margin_sensitivity_drivers)
    if priors.margin_sensitivity > 0.65:
        pressures.append("margin_sensitivity_high")
    return list(dict.fromkeys(pressures))


def impact_weights_for_drivers(drivers: list[BusinessDriver]) -> ImpactWeights:
    w = ImpactWeights()
    if "cash_conversion" in drivers:
        w.cash = 0.4
        w.revenue = 0.15
    if "gross_margin" in drivers:
        w.margin = 0.35
    if "retention" in drivers:
        w.retention = 0.3
    if "risk_exposure" in drivers:
        w.risk = 0.25
    return w


def driver_impact_score(driver: BusinessDriver) -> BusinessImpactScore:
    score = BusinessImpactScore()
    mapping = {
        "revenue_growth": ("revenue", 0.8),
        "gross_margin": ("margin", 0.85),
        "retention": ("retention", 0.8),
        "cash_conversion": ("cash", 0.85),
        "capacity_utilization": ("strategic", 0.6),
        "customer_acquisition": ("revenue", 0.7),
        "risk_exposure": ("risk", 0.75),
        "working_capital": ("cash", 0.7),
    }
    field, val = mapping.get(driver, ("strategic", 0.5))
    setattr(score, field, val)
    return score
