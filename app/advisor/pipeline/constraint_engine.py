"""Constraint hierarchy — what blocks implementation."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessContext,
    Constraint,
    ConstraintProfile,
    ConstraintType,
    EvidenceStrength,
)
from app.advisor.pipeline.discovery_models import FactGraph

_CONSTRAINT_SIGNALS: dict[ConstraintType, tuple[str, ...]] = {
    "FINANCIAL": ("budget", "cost", "afford", "cash flow", "capital", "funding"),
    "ORGANIZATIONAL": ("union", "headcount", "hiring freeze", "reorg", "politics"),
    "REGULATORY": ("compliance", "regulation", "hipaa", "licensing", "audit"),
    "TECHNOLOGICAL": ("erp", "legacy", "cannot replace", "integration", "system"),
    "DATA": ("no data", "data quality", "historical data", "spreadsheet"),
    "CULTURAL": ("resistance", "culture", "change management", "adoption"),
    "TIME": ("deadline", "timeline", "urgent", "90 day", "quarter"),
}


def build_constraint_profile(
    fact_graph: FactGraph,
    business_context: BusinessContext,
) -> ConstraintProfile:
    blob = fact_graph.blob()
    constraints: list[Constraint] = []

    for ctype, signals in _CONSTRAINT_SIGNALS.items():
        for sig in signals:
            if sig in blob:
                fact_ids = [f.id for f in fact_graph.facts if sig in f.normalized]
                strength: EvidenceStrength = "observed" if fact_ids else "inferred"
                constraints.append(
                    Constraint(
                        type=ctype,
                        description=sig,
                        severity=0.7 if ctype in ("REGULATORY", "FINANCIAL") else 0.55,
                        evidence_strength=strength,
                        evidence_fact_ids=fact_ids[:3],
                    )
                )

    for fact in fact_graph.facts_by_category("constraint"):
        ctype: ConstraintType = "ORGANIZATIONAL"
        n = fact.normalized
        if any(s in n for s in _CONSTRAINT_SIGNALS["FINANCIAL"]):
            ctype = "FINANCIAL"
        elif any(s in n for s in _CONSTRAINT_SIGNALS["REGULATORY"]):
            ctype = "REGULATORY"
        elif any(s in n for s in _CONSTRAINT_SIGNALS["TECHNOLOGICAL"]):
            ctype = "TECHNOLOGICAL"
        constraints.append(
            Constraint(
                type=ctype,
                description=fact.text[:120],
                severity=0.75,
                evidence_strength=fact.evidence_strength,
                evidence_fact_ids=[fact.id],
            )
        )

    for reg in business_context.regulatory_constraints:
        constraints.append(
            Constraint(
                type="REGULATORY",
                description=reg,
                severity=0.8,
                evidence_strength="inferred",
            )
        )

    seen: set[str] = set()
    unique: list[Constraint] = []
    for c in constraints:
        key = f"{c.type}:{c.description}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    types_found = {c.type for c in unique}
    coverage = min(1.0, 0.25 * len(types_found) + 0.1 * len(unique))
    if fact_graph.facts_by_category("constraint"):
        coverage = min(1.0, coverage + 0.2)
    blocking = [c.type for c in unique if c.severity >= 0.7]

    return ConstraintProfile(
        constraints=unique,
        coverage=round(coverage, 2),
        blocking_types=list(dict.fromkeys(blocking)),
    )


def constraint_blocks_intervention(
    intervention_description: str,
    profile: ConstraintProfile,
) -> bool:
    desc = intervention_description.lower()
    for c in profile.constraints:
        if c.severity < 0.65:
            continue
        if c.type == "FINANCIAL" and any(w in desc for w in ("expensive", "replace", "new system")):
            return True
        if c.type == "TECHNOLOGICAL" and "replace" in c.description and "replace" in desc:
            return True
        if c.type == "ORGANIZATIONAL" and "restructur" in desc:
            return True
        if c.type == "DATA" and any(w in desc for w in ("ml", "forecast", "predict")):
            if "no data" in c.description or "historical" in c.description:
                return True
    return False
