"""Root cause confidence computation."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    CapabilityGap,
    CausalGraph,
    ConfidenceState,
    RootCauseConfidence,
)

VALIDATION_THRESHOLD = 0.72
COMPETING_MARGIN = 0.10


def compute_root_cause_confidence(
    causal_graph: CausalGraph,
    capability_gaps: list[CapabilityGap],
) -> ConfidenceState:
    causes = causal_graph.root_causes()
    if not causes:
        causes = [n for n in causal_graph.nodes if n.kind == "cause"]

    root_causes: list[RootCauseConfidence] = []
    for node in causes:
        gap_id = None
        for gap in capability_gaps:
            if gap.specialization_label and gap.specialization_label in node.label:
                gap_id = f"{gap.universal_id}:{gap.specialization_label}"
                break
        root_causes.append(
            RootCauseConfidence(
                cause_id=node.id,
                label=node.label,
                confidence=round(node.confidence, 2),
                evidence_fact_ids=node.evidence_fact_ids,
                capability_gap_id=gap_id,
                evidence_strength=node.evidence_strength,
            )
        )

    root_causes.sort(key=lambda r: r.confidence, reverse=True)
    top = root_causes[0].confidence if root_causes else 0.0
    competing = False
    if len(root_causes) >= 2:
        competing = (root_causes[0].confidence - root_causes[1].confidence) < COMPETING_MARGIN

    validation_ready = top >= VALIDATION_THRESHOLD and not competing
    return ConfidenceState(
        root_causes=root_causes,
        top_confidence=top,
        validation_ready=validation_ready,
        competing_within_margin=competing,
    )
