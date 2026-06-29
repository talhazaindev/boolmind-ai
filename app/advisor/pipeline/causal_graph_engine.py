"""Causal graph construction from patterns, capabilities, stakeholders."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessDriver,
    BusinessModelProfile,
    CapabilityGap,
    CausalEdge,
    CausalGraph,
    CausalNode,
    IncentiveConflict,
    PatternMatch,
    ValueChainState,
)
from app.advisor.pipeline.discovery_models import FactGraph
from app.advisor.pipeline.stakeholder_engine import conflict_node_confidence


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:40].strip("_")


def build_causal_graph(
    fact_graph: FactGraph,
    pattern_matches: list[PatternMatch],
    business_model: BusinessModelProfile,
    capability_gaps: list[CapabilityGap],
    incentive_conflicts: list[IncentiveConflict],
    value_chain: ValueChainState,
    economic_drivers: list[BusinessDriver],
) -> CausalGraph:
    nodes: list[CausalNode] = []
    edges: list[CausalEdge] = []
    seen: set[str] = set()

    def add_node(kind: str, label: str, drivers: list[BusinessDriver], conf: float, **kw: object) -> str:
        nid = f"{kind}_{_slug(label)}"
        if nid in seen:
            return nid
        seen.add(nid)
        nodes.append(
            CausalNode(
                id=nid,
                kind=kind,  # type: ignore[arg-type]
                label=label,
                business_drivers=drivers,
                confidence=conf,
                evidence_strength=kw.get("strength", "inferred"),  # type: ignore[arg-type]
                evidence_fact_ids=kw.get("fact_ids", []),  # type: ignore[arg-type]
            )
        )
        return nid

    for outcome in fact_graph.facts_by_category("outcome"):
        add_node("outcome", outcome.text[:80], economic_drivers[:2] or ["revenue_growth"], 0.8, fact_ids=[outcome.id], strength=outcome.evidence_strength)

    for symptom in fact_graph.facts_by_category("symptom"):
        drivers: list[BusinessDriver] = economic_drivers[:1] or ["capacity_utilization"]
        add_node(
            "symptom",
            symptom.text[:80],
            drivers,
            0.7,
            fact_ids=[symptom.id],
            strength=symptom.evidence_strength,
        )
        # Symptoms with problem language can seed causes
        add_node(
            "cause",
            f"driver of: {symptom.text[:50]}",
            drivers,
            0.55,
            fact_ids=[symptom.id],
            strength=symptom.evidence_strength,
        )

    for gap in capability_gaps[:4]:
        label = gap.specialization_label or gap.universal_id.replace("_", " ")
        add_node(
            "cause",
            f"{label} capability gap",
            gap.linked_drivers or ["gross_margin"],
            gap.severity,
            strength=gap.evidence_strength,
            fact_ids=gap.evidence_fact_ids,
        )

    for match in pattern_matches[:2]:
        for chain_link in match.pattern.typical_causal_chains:
            add_node(
                "cause",
                chain_link.replace("_", " "),
                economic_drivers[:2] or ["gross_margin"],
                0.5 + match.confidence * 0.3,
                strength=match.evidence_strength,
                fact_ids=match.evidence_fact_ids,
            )

    for driver in business_model.margin_sensitivity_drivers[:3]:
        add_node("cause", driver.replace("_", " "), ["gross_margin"], 0.55 + business_model.confidence * 0.2)

    for change in fact_graph.facts_by_category("organizational_change"):
        add_node(
            "cause",
            f"impact of {change.text[:60]}",
            economic_drivers[:1] or ["gross_margin"],
            0.72,
            strength=change.evidence_strength,
            fact_ids=[change.id],
        )

    for conflict in incentive_conflicts[:2]:
        conf = conflict_node_confidence(conflict)
        add_node(
            "cause",
            f"{conflict.stakeholder_a} vs {conflict.stakeholder_b}: {conflict.conflict_reason}",
            ["capacity_utilization"],
            conf,
            strength=conflict.evidence_strength,
        )

    if value_chain.active and value_chain.breakdown_stage:
        add_node(
            "cause",
            f"{value_chain.breakdown_stage.replace('_', ' ')} bottleneck",
            ["capacity_utilization"],
            value_chain.relevance_confidence,
        )

    causes = [n for n in nodes if n.kind == "cause"]
    outcomes = [n for n in nodes if n.kind == "outcome"]
    symptoms = [n for n in nodes if n.kind == "symptom"]

    for cause in causes:
        for outcome in outcomes:
            edges.append(
                CausalEdge(
                    source_id=cause.id,
                    target_id=outcome.id,
                    relation="contributes_to",
                    confidence=cause.confidence * 0.85,
                    uncertainty=round(1.0 - cause.confidence * 0.85, 2),
                )
            )
        for symptom in symptoms:
            edges.append(
                CausalEdge(
                    source_id=cause.id,
                    target_id=symptom.id,
                    relation="causes",
                    confidence=cause.confidence * 0.75,
                    uncertainty=round(1.0 - cause.confidence * 0.75, 2),
                )
            )

    return CausalGraph(nodes=nodes, edges=edges)
