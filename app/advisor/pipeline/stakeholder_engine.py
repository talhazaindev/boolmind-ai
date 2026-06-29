"""Stakeholder profiles and incentive conflicts."""

from __future__ import annotations

import re

from app.advisor.pipeline.business_systems_models import (
    EvidenceStrength,
    IncentiveConflict,
    StakeholderProfile,
)

from app.advisor.pipeline.discovery_models import FactGraph

INCENTIVE_CONFLICT_PRIOR = 0.85

_STAKEHOLDER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sales": ("sales", "account executive", "ae ", "revenue team"),
    "operations": ("operations", "ops", "fulfillment", "dispatch"),
    "finance": ("finance", "cfo", "accounting", "controller"),
    "compliance": ("compliance", "legal", "risk", "audit"),
    "leadership": ("ceo", "leadership", "executive", "management"),
    "workforce": (
        "clinician",
        "veterinarian",
        "technician",
        "nurse",
        "provider",
        "field staff",
        "frontline",
        "staff turnover",
        "employee turnover",
    ),
}

_CONFLICT_PAIRS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("sales", "operations", "speed vs quality", ("overpromis", "speed", "capacity", "delivery")),
    ("sales", "finance", "growth vs cash", ("discount", "terms", "cash", "margin")),
    ("operations", "compliance", "throughput vs control", ("compliance", "approval", "backlog")),
]


def extract_stakeholder_profiles(fact_graph: FactGraph) -> list[StakeholderProfile]:
    blob = fact_graph.blob()
    profiles: list[StakeholderProfile] = []
    for name, keywords in _STAKEHOLDER_KEYWORDS.items():
        if not any(k in blob for k in keywords):
            continue
        objectives: list[str] = []
        pressures: list[str] = []
        fact_ids: list[str] = []
        for fact in fact_graph.facts:
            if any(k in fact.normalized for k in keywords):
                fact_ids.append(fact.id)
                if fact.category == "stakeholder_theory":
                    pressures.append(fact.text[:80])
        profiles.append(
            StakeholderProfile(
                stakeholder=name,
                objectives=objectives,
                pressures=pressures,
                evidence_strength="inferred" if fact_ids else "speculated",
                evidence_fact_ids=fact_ids[:5],
            )
        )
    return profiles


def detect_incentive_conflicts(
    profiles: list[StakeholderProfile],
    fact_graph: FactGraph,
) -> list[IncentiveConflict]:
    blob = fact_graph.blob()
    conflicts: list[IncentiveConflict] = []
    active = {p.stakeholder for p in profiles}

    for a, b, reason, signals in _CONFLICT_PAIRS:
        if a not in active and b not in active:
            if not any(s in blob for s in signals):
                continue
        if not any(s in blob for s in signals):
            continue
        symptom_ids = [f.id for f in fact_graph.facts_by_category("symptom")]
        strength: EvidenceStrength = "speculated"
        if any(f.category == "stakeholder_theory" for f in fact_graph.facts):
            strength = "inferred"
        conflicts.append(
            IncentiveConflict(
                stakeholder_a=a,
                stakeholder_b=b,
                conflict_reason=reason,
                severity=0.55,
                evidence_strength=strength,
                linked_symptom_ids=symptom_ids[:3],
            )
        )

    for fact in fact_graph.facts_by_category("stakeholder_theory"):
        m = re.search(r"(\w+)\s+blames?\s+(\w+)", fact.normalized)
        if m:
            conflicts.append(
                IncentiveConflict(
                    stakeholder_a=m.group(1),
                    stakeholder_b=m.group(2),
                    conflict_reason="stated blame pattern",
                    severity=0.5,
                    evidence_strength=fact.evidence_strength,
                    linked_symptom_ids=[fact.id],
                )
            )

    org_changes = fact_graph.facts_by_category("organizational_change")
    for change in org_changes:
        subject = change.normalized
        if any(k in subject for k in ("compensation", "incentive", "commission", "bonus", "pay")):
            conflicts.append(
                IncentiveConflict(
                    stakeholder_a="workforce",
                    stakeholder_b="leadership",
                    conflict_reason="incentive redesign vs operating targets",
                    severity=0.78,
                    evidence_strength=change.evidence_strength,
                    linked_symptom_ids=[change.id],
                )
            )
        elif any(k in subject for k in ("pricing", "fee", "rate card", "revenue model")):
            conflicts.append(
                IncentiveConflict(
                    stakeholder_a="sales",
                    stakeholder_b="finance",
                    conflict_reason="pricing change vs margin targets",
                    severity=0.72,
                    evidence_strength=change.evidence_strength,
                    linked_symptom_ids=[change.id],
                )
            )

    return conflicts


def conflict_node_confidence(conflict: IncentiveConflict) -> float:
    strength_map = {"observed": 1.0, "inferred": 0.75, "speculated": 0.45}
    base = conflict.severity * strength_map.get(conflict.evidence_strength, 0.5)
    return round(base * INCENTIVE_CONFLICT_PRIOR, 3)


def strength_to_float(strength: str) -> float:
    return {"observed": 1.0, "inferred": 0.75, "speculated": 0.45}.get(strength, 0.5)
