"""Business pattern matching — cross-industry patterns before causal reasoning."""

from __future__ import annotations

import re

from app.advisor.pipeline.business_systems_models import (
    BusinessPattern,
    EvidenceStrength,
    PatternMatch,
)
from app.advisor.pipeline.discovery_models import FactGraph

_BUSINESS_PATTERNS: list[BusinessPattern] = [
    BusinessPattern(
        pattern_id="revenue_up_margin_down",
        label="Revenue Up / Margin Down",
        driver_signature={"revenue": "up", "margin": "down"},
        symptom_signals=("margin", "profit", "cost", "revenue", "growing"),
        typical_capability_gaps=("collect_revenue", "make_decisions"),
        typical_causal_chains=("pricing_pressure", "cost_inflation", "mix_shift"),
    ),
    BusinessPattern(
        pattern_id="revenue_up_cash_down",
        label="Revenue Up / Cash Down",
        driver_signature={"revenue": "up", "cash": "down"},
        symptom_signals=("cash", "revenue", "invoice", "collection", "payment"),
        typical_capability_gaps=("collect_revenue",),
        typical_causal_chains=("invoicing_delay", "collections_friction", "payment_terms"),
    ),
    BusinessPattern(
        pattern_id="growth_retention_down",
        label="Growth / Retention Down",
        driver_signature={"acquisition": "up", "retention": "down"},
        symptom_signals=("churn", "retention", "growth", "acquisition", "leaving", "overpromis"),
        typical_capability_gaps=("retain_customers", "deliver_value"),
        typical_causal_chains=("onboarding_gap", "value_delivery", "support_quality"),
    ),
    BusinessPattern(
        pattern_id="backlog_hiring_up",
        label="Backlog / Hiring Up",
        driver_signature={"backlog": "up", "hiring": "up"},
        symptom_signals=("backlog", "hiring", "headcount", "queue", "capacity"),
        typical_capability_gaps=("manage_capacity", "deliver_value"),
        typical_causal_chains=("capacity_shortage", "process_inefficiency"),
    ),
    BusinessPattern(
        pattern_id="complaints_sla_stable",
        label="Complaints Up / SLA Stable",
        driver_signature={"complaints": "up", "sla": "stable"},
        symptom_signals=("complaint", "sla", "quality", "customer"),
        typical_capability_gaps=("deliver_value", "retain_customers"),
        typical_causal_chains=("expectation_gap", "incentive_misalignment"),
    ),
]

_UP_SIGNALS = ("grow", "growing", "increase", "up", "rising", "higher")
_DOWN_SIGNALS = ("shrink", "declin", "down", "falling", "lower", "unstable", "worse")


def _blob(fact_graph: FactGraph) -> str:
    return fact_graph.blob()


def _has_direction(blob: str, topic: str, direction: str) -> bool:
    signals = _UP_SIGNALS if direction == "up" else _DOWN_SIGNALS
    for sig in signals:
        if re.search(rf"{topic}.{{0,40}}{sig}|{sig}.{{0,40}}{topic}", blob):
            return True
    return False


def _pattern_score(pattern: BusinessPattern, blob: str, fact_graph: FactGraph) -> tuple[float, list[str], EvidenceStrength]:
    hits = [s for s in pattern.symptom_signals if s in blob]
    if not hits:
        return 0.0, [], "speculated"

    score = min(0.95, 0.35 + 0.1 * len(hits))
    fact_ids: list[str] = []
    for fact in fact_graph.facts:
        if any(s in fact.normalized for s in hits):
            fact_ids.append(fact.id)
            score = min(0.98, score + 0.05)

    sig = pattern.driver_signature
    if sig.get("revenue") == "up" and _has_direction(blob, "revenue", "up"):
        score += 0.1
    if sig.get("margin") == "down" and _has_direction(blob, "margin", "down"):
        score += 0.1
    if sig.get("cash") == "down" and ("cash" in blob and any(s in blob for s in _DOWN_SIGNALS)):
        score += 0.1
    if "churn" in blob:
        score += 0.2
        if sig.get("retention") == "down" or pattern.pattern_id == "growth_retention_down":
            score += 0.1

    strength: EvidenceStrength = "observed" if len(fact_ids) >= 2 else "inferred"
    if score < pattern.pattern_confidence_threshold:
        return 0.0, fact_ids, strength
    return min(0.99, score), fact_ids, strength


def match_patterns(fact_graph: FactGraph, message: str = "") -> list[PatternMatch]:
    """Match cross-industry business patterns from fact graph."""
    blob = f"{fact_graph.blob()} {message.lower()}"
    matches: list[PatternMatch] = []
    for pattern in _BUSINESS_PATTERNS:
        score, fact_ids, strength = _pattern_score(pattern, blob, fact_graph)
        if score >= pattern.pattern_confidence_threshold:
            matches.append(
                PatternMatch(
                    pattern=pattern,
                    confidence=round(score, 2),
                    evidence_fact_ids=fact_ids,
                    evidence_strength=strength,
                )
            )
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches
