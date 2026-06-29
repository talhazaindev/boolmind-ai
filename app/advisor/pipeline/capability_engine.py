"""Universal capability model — no operating-model templates."""

from __future__ import annotations

import re

from app.advisor.pipeline.business_systems_models import (
    BusinessDriver,
    BusinessModelProfile,
    CapabilityGap,
    CapabilitySpecialization,
    EvidenceStrength,
    PatternMatch,
    UniversalCapability,
)

from app.advisor.pipeline.discovery_models import FactGraph

_CAPABILITY_SIGNALS: dict[UniversalCapability, tuple[str, ...]] = {
    "acquire_customers": ("lead", "marketing", "acquisition", "prospect", "pipeline"),
    "convert_customers": ("sales", "conversion", "close", "demo", "qualification"),
    "deliver_value": ("delivery", "fulfillment", "service", "production", "dispatch"),
    "retain_customers": ("retention", "churn", "renewal", "loyalty"),
    "collect_revenue": ("billing", "invoice", "pricing", "payment", "collections"),
    "manage_risk": ("compliance", "risk", "audit", "regulatory", "underwriting"),
    "manage_capacity": ("capacity", "scheduling", "staffing", "utilization", "backlog"),
    "manage_information": ("data", "reporting", "spreadsheet", "visibility", "forecast"),
    "make_decisions": ("approval", "prioritiz", "decision", "planning", "forecast"),
}

_GAP_OUTCOME_SIGNALS: dict[str, tuple[UniversalCapability, BusinessDriver]] = {
    "margin": ("collect_revenue", "gross_margin"),
    "churn": ("retain_customers", "retention"),
    "cash": ("collect_revenue", "cash_conversion"),
    "backlog": ("manage_capacity", "capacity_utilization"),
    "approval": ("make_decisions", "capacity_utilization"),
}


def _specialization_label(blob: str, universal_id: UniversalCapability) -> str | None:
    patterns: dict[UniversalCapability, tuple[str, ...]] = {
        "manage_information": ("demand planning", "forecasting", "reporting"),
        "collect_revenue": ("pricing", "invoicing", "collections"),
        "manage_capacity": ("scheduling", "dispatch", "routing"),
        "make_decisions": ("approval", "prioritization"),
    }
    for phrase in patterns.get(universal_id, ()):
        if phrase in blob:
            return phrase
    return None


def infer_capabilities(fact_graph: FactGraph, message: str = "") -> list[CapabilitySpecialization]:
    blob = f"{fact_graph.blob()} {message.lower()}"
    caps: list[CapabilitySpecialization] = []
    for cap_id, signals in _CAPABILITY_SIGNALS.items():
        hits = [s for s in signals if s in blob]
        if not hits:
            continue
        fact_ids = [f.id for f in fact_graph.facts if any(s in f.normalized for s in hits)]
        strength: EvidenceStrength = "observed" if len(fact_ids) >= 2 else "inferred"
        spec = _specialization_label(blob, cap_id)
        caps.append(
            CapabilitySpecialization(
                universal_id=cap_id,
                label=spec or cap_id.replace("_", " "),
                evidence_strength=strength,
                confidence=min(0.95, 0.4 + 0.1 * len(hits)),
                evidence_fact_ids=fact_ids[:5],
            )
        )
    return caps


def detect_capability_gaps(
    capabilities: list[CapabilitySpecialization],
    fact_graph: FactGraph,
    pattern_matches: list[PatternMatch],
    business_model: BusinessModelProfile,
    message: str = "",
) -> list[CapabilityGap]:
    blob = f"{fact_graph.blob()} {message.lower()}"
    gaps: list[CapabilityGap] = []
    active_ids = {c.universal_id for c in capabilities}

    for topic, (cap_id, driver) in _GAP_OUTCOME_SIGNALS.items():
        if topic in blob and any(w in blob for w in ("problem", "issue", "down", "slow", "weak")):
            gaps.append(
                CapabilityGap(
                    universal_id=cap_id,
                    specialization_label=_specialization_label(blob, cap_id),
                    severity=0.65,
                    evidence_strength="inferred",
                    linked_drivers=[driver],
                    evidence_fact_ids=[],
                )
            )

    for match in pattern_matches[:2]:
        for cap_name in match.pattern.typical_capability_gaps:
            if cap_name not in _CAPABILITY_SIGNALS:
                continue
            uid: UniversalCapability = cap_name  # type: ignore[assignment]
            gaps.append(
                CapabilityGap(
                    universal_id=uid,
                    severity=0.55 + match.confidence * 0.2,
                    evidence_strength=match.evidence_strength,
                    linked_pattern_ids=[match.pattern.pattern_id],
                    evidence_fact_ids=match.evidence_fact_ids,
                )
            )

    for driver in business_model.margin_sensitivity_drivers:
        if driver in ("pricing", "forecasting"):
            gaps.append(
                CapabilityGap(
                    universal_id="collect_revenue" if driver == "pricing" else "manage_information",
                    specialization_label=driver,
                    severity=0.6,
                    evidence_strength="inferred",
                    linked_drivers=["gross_margin"],
                )
            )

    seen: set[str] = set()
    unique: list[CapabilityGap] = []
    for gap in gaps:
        key = f"{gap.universal_id}:{gap.specialization_label}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(gap)
    return unique
