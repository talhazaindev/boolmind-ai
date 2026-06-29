"""Hard stage exits for conversation progression."""

from __future__ import annotations

from app.advisor.types import ConversationPipelineStage, HypothesisSnapshot, SessionMetadata

MIN_CONFIRMED_BOTTLENECKS_FOR_SALES = 2
BOTTLENECK_CONFIRM_CONFIDENCE = 0.75
QUALIFICATION_EVIDENCE_THRESHOLD = 0.65
HYPOTHESIS_EVIDENCE_THRESHOLD = 0.80


def qualification_bundle_complete(meta: SessionMetadata, snapshot: HypothesisSnapshot) -> bool:
    """Industry + scale + process + pain + impact — minimum for hypothesis work."""
    return snapshot.overall_confidence >= QUALIFICATION_EVIDENCE_THRESHOLD


def discovery_exit_met(meta: SessionMetadata, snapshot: HypothesisSnapshot) -> bool:
    has_business = bool(
        snapshot.active_business_vertical
        or meta.industry
        or meta.business_type
        or snapshot.business_model != "unknown"
    )
    has_pain = bool(meta.pain_point or snapshot.primary_bottleneck)
    has_scale = bool(snapshot.scale_indicators or meta.data_context)
    return has_business and has_pain and has_scale


def diagnose_exit_met(snapshot: HypothesisSnapshot) -> bool:
    bottleneck_conf = snapshot.confidence_scores.get("ops", 0.0)
    if snapshot.primary_bottleneck and bottleneck_conf >= BOTTLENECK_CONFIRM_CONFIDENCE:
        return True
    if (
        snapshot.primary_bottleneck
        and snapshot.overall_confidence >= QUALIFICATION_EVIDENCE_THRESHOLD
    ):
        return True
    return (
        snapshot.confirmed_bottleneck_count >= 1
        and snapshot.overall_confidence >= HYPOTHESIS_EVIDENCE_THRESHOLD
    )


def solutioning_allowed(snapshot: HypothesisSnapshot) -> bool:
    return (
        snapshot.confirmed_bottleneck_count >= 1
        and snapshot.overall_confidence >= HYPOTHESIS_EVIDENCE_THRESHOLD
        and snapshot.conversation_stage in ("HYPOTHESIS_VALIDATION", "SOLUTION_ALIGNMENT")
    )


def compute_conversation_stage(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
) -> ConversationPipelineStage:
    if snapshot.hypothesis_status == "conflicted":
        return "DISCOVERY"

    if not discovery_exit_met(meta, snapshot):
        if meta.message_count <= 3:
            return "DISCOVERY"
        return "CONSTRAINT_MAPPING"

    if not diagnose_exit_met(snapshot):
        return "BOTTLENECK_ISOLATION"

    if qualification_bundle_complete(meta, snapshot) and snapshot.primary_bottleneck:
        return "HYPOTHESIS_VALIDATION"

    if snapshot.confirmed_bottleneck_count >= MIN_CONFIRMED_BOTTLENECKS_FOR_SALES:
        return "HYPOTHESIS_VALIDATION"

    return "BOTTLENECK_ISOLATION"
