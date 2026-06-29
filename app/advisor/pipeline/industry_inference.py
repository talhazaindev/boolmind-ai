"""Probabilistic industry inference — evidence only, never routing."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import IndustryHypothesis
from app.advisor.pipeline.discovery_models import FactGraph

_INDUSTRY_SIGNALS: dict[str, tuple[str, ...]] = {
    "saas": ("saas", "software", "subscription", "mrr", "arr"),
    "healthcare": ("patient", "clinic", "hospital", "hipaa", "ehr"),
    "dental": ("dental", "dentist", "chair"),
    "veterinary": ("veterinary", "vet clinic", "animal", "pet"),
    "insurance": ("insurance", "underwriting", "brokerage", "policy"),
    "logistics": ("logistics", "dispatch", "fleet", "shipment", "truck"),
    "manufacturing": ("manufacturing", "factory", "production line"),
    "retail": ("retail", "store", "sku", "inventory"),
    "consulting": ("consulting", "billable", "engagement", "advisory"),
    "financial_services": ("lending", "loan", "bank", "credit"),
    "legal": ("law firm", "legal", "attorney"),
}


def infer_industry_hypotheses(fact_graph: FactGraph) -> list[IndustryHypothesis]:
    blob = fact_graph.blob()
    hyps: list[IndustryHypothesis] = []
    for label, signals in _INDUSTRY_SIGNALS.items():
        hits = [s for s in signals if s in blob]
        if not hits:
            continue
        fact_ids = [f.id for f in fact_graph.facts if any(s in f.normalized for s in hits)]
        confidence = min(0.95, 0.35 + 0.12 * len(hits))
        hyps.append(
            IndustryHypothesis(
                label=label,
                confidence=round(confidence, 2),
                evidence_fact_ids=fact_ids[:5],
            )
        )
    hyps.sort(key=lambda h: h.confidence, reverse=True)
    return hyps


def regulatory_priors(industries: list[IndustryHypothesis]) -> list[str]:
    priors: list[str] = []
    for hyp in industries:
        if hyp.confidence < 0.5:
            continue
        if hyp.label in ("healthcare", "dental", "veterinary"):
            priors.append("healthcare_regulatory")
        if hyp.label == "insurance":
            priors.append("insurance_regulatory")
        if hyp.label == "financial_services":
            priors.append("financial_regulatory")
    return list(dict.fromkeys(priors))
