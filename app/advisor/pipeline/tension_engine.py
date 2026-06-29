"""Tension detection — competing explanations, contradictions, evidence gaps."""

from __future__ import annotations

from app.advisor.pipeline.discovery_models import (
    DynamicHypothesis,
    EvidenceGap,
    ExtractedFact,
    FactGraph,
    Tension,
)
from app.advisor.pipeline.evidence_extractor import _metric_phrase, _slug


def hypotheses_from_facts(fact_graph: FactGraph) -> list[DynamicHypothesis]:
    """Generate hypotheses dynamically from extracted facts — no cause catalog."""
    hypotheses: list[DynamicHypothesis] = []
    seen: set[str] = set()

    for fact in fact_graph.facts_by_category("stakeholder_theory"):
        label = fact.text
        hid = f"hyp_{_slug(label)}"
        if hid in seen:
            continue
        seen.add(hid)
        hypotheses.append(
            DynamicHypothesis(
                id=hid,
                label=label,
                metric_phrase=_metric_phrase(label),
                source="stakeholder",
                confidence=fact.confidence,
                supporting_fact_ids=[fact.id],
                evidence_strength=0.9,
            )
        )

    for fact in fact_graph.facts_by_category("organizational_change"):
        label = fact.text
        hid = f"hyp_change_{_slug(label)}"
        if hid in seen:
            continue
        seen.add(hid)
        hypotheses.append(
            DynamicHypothesis(
                id=hid,
                label=f"impact of: {label}",
                metric_phrase=_metric_phrase(label),
                source="inferred",
                confidence=fact.confidence,
                supporting_fact_ids=[fact.id],
                evidence_strength=0.92,
            )
        )

    for fact in fact_graph.facts_by_category("stated_hypothesis"):
        label = fact.text
        hid = f"hyp_belief_{_slug(label)}"
        if hid in seen:
            continue
        seen.add(hid)
        hypotheses.append(
            DynamicHypothesis(
                id=hid,
                label=f"stated cause: {label}",
                metric_phrase=_metric_phrase(label),
                source="inferred",
                confidence=fact.confidence * 0.75,
                supporting_fact_ids=[fact.id],
                evidence_strength=0.55,
            )
        )

    for fact in fact_graph.facts_by_category("symptom"):
        label = fact.text
        if any(
            label in o.text or o.text in label
            for o in fact_graph.facts_by_category("outcome")
        ):
            continue
        hid = f"hyp_symptom_{_slug(label)}"
        if hid in seen:
            continue
        seen.add(hid)
        hypotheses.append(
            DynamicHypothesis(
                id=hid,
                label=label,
                metric_phrase=_metric_phrase(label),
                source="symptom",
                confidence=fact.confidence * 0.85,
                supporting_fact_ids=[fact.id],
                evidence_strength=0.65,
            )
        )

    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    return hypotheses[:6]


def detect_competing_explanations(
    hypotheses: list[DynamicHypothesis],
    fact_graph: FactGraph,
) -> Tension | None:
    theories = [h for h in hypotheses if h.source == "stakeholder"]
    if len(theories) < 2:
        return None
    return Tension(
        kind="competing_explanations",
        description="Leadership cites multiple competing explanations for the stated problem.",
        hypothesis_ids=[h.id for h in theories[:5]],
        fact_ids=[fid for h in theories for fid in h.supporting_fact_ids],
        priority=0.95,
    )


def detect_outcome_contradictions(fact_graph: FactGraph) -> list[Tension]:
    tensions: list[Tension] = []
    outcomes = fact_graph.facts_by_category("outcome")
    growth = [o for o in outcomes if "growth" in o.normalized or "up" in o.normalized]
    decline = [
        o
        for o in outcomes
        if any(k in o.normalized for k in ("declin", "dropped", "shrinking", "churn"))
    ]
    if growth and decline:
        tensions.append(
            Tension(
                kind="outcome_contradiction",
                description="Revenue or volume is growing while another key outcome is declining.",
                fact_ids=[f.id for f in growth + decline],
                priority=0.85,
            )
        )
    return tensions


def detect_missing_evidence(
    fact_graph: FactGraph,
    hypotheses: list[DynamicHypothesis],
    *,
    skipped_keys: set[str] | None = None,
) -> list[EvidenceGap]:
    gaps: list[EvidenceGap] = []
    skipped = skipped_keys or set()
    blob = fact_graph.blob()

    def _solution_forward() -> bool:
        return any(
            s in blob
            for s in (
                "want to automate",
                "want a solution",
                "looking for a solution",
                "automate everything",
                "help me reduce labor",
                "maximizing my profit",
                "need a solution",
            )
        )

    if (
        hypotheses
        and not fact_graph.timeline_phrase
        and "timeline" not in skipped
        and not _solution_forward()
    ):
        gaps.append(
            EvidenceGap(
                id="gap_timeline",
                description="No timeline stated for when the problem accelerated.",
                priority=0.55,
                suggested_probe="When did you first notice this shift — roughly which quarter or month?",
            )
        )

    theories = [h for h in hypotheses if h.source == "stakeholder"]
    change_hyps = [h for h in hypotheses if h.source == "inferred" and h.id.startswith("hyp_change_")]
    belief_hyps = [h for h in hypotheses if h.id.startswith("hyp_belief_")]

    if change_hyps and (belief_hyps or theories):
        gaps.append(
            EvidenceGap(
                id="gap_change_vs_stated_cause",
                description="Organizational change may compete with stated bottleneck theories.",
                priority=0.93,
            )
        )

    if len(theories) >= 2 and not fact_graph.primary_outcome:
        gaps.append(
            EvidenceGap(
                id="gap_outcome",
                description="Competing theories exist but the primary business outcome is unclear.",
                priority=0.7,
                suggested_probe="Which business outcome matters most right now — retention, margin, throughput, or something else?",
            )
        )

    if len(theories) >= 2:
        gaps.append(
            EvidenceGap(
                id="gap_discriminative_metric",
                description="Multiple theories need a metric comparison to discriminate.",
                priority=0.92,
            )
        )

    if not fact_graph.facts_by_category("scale") and len(theories) >= 2:
        gaps.append(
            EvidenceGap(
                id="gap_scale",
                description="Scale context would help interpret competing theories.",
                priority=0.35,
                suggested_probe="Roughly what volume or scale are we talking about — orders, customers, or revenue band?",
            )
        )

    gaps.sort(key=lambda g: g.priority, reverse=True)
    return gaps


def analyze_tensions(
    fact_graph: FactGraph,
    hypotheses: list[DynamicHypothesis],
    *,
    skipped_keys: set[str] | None = None,
) -> tuple[list[Tension], list[EvidenceGap]]:
    tensions: list[Tension] = []
    competing = detect_competing_explanations(hypotheses, fact_graph)
    if competing:
        tensions.append(competing)
    tensions.extend(detect_outcome_contradictions(fact_graph))
    gaps = detect_missing_evidence(fact_graph, hypotheses, skipped_keys=skipped_keys)
    return tensions, gaps
