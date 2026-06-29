"""L6 — deterministic pipeline and funnel stage advancement."""

from __future__ import annotations

from app.advisor.orchestrator.conversation_progression import (
    diagnose_exit_met,
    discovery_exit_met,
    solutioning_allowed,
)
from app.advisor.orchestrator.tool_gating import STAGE_ORDER
from app.advisor.types import ConversationStage, HypothesisSnapshot, SessionMetadata


def promote_funnel_stage(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
) -> ConversationStage:
    """Monotonic funnel promotion on critical path (T0 — no LLM eval required)."""
    current = meta.stage_reached
    idx = STAGE_ORDER.get(current, 0)

    if snapshot.hypothesis_status == "conflicted":
        return current

    target_idx = idx

    if discovery_exit_met(meta, snapshot):
        target_idx = max(target_idx, STAGE_ORDER["INTEREST"])

    if diagnose_exit_met(snapshot):
        target_idx = max(target_idx, STAGE_ORDER["QUALIFY"])

    if solutioning_allowed(snapshot):
        target_idx = max(target_idx, STAGE_ORDER["CAPTURE"])

    if meta.visitor_name and meta.collected_email:
        target_idx = max(target_idx, STAGE_ORDER["CAPTURE"])

    for stage, order in STAGE_ORDER.items():
        if order == target_idx:
            return stage
    return current


def architecture_fast_path_qualify(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    deferred_architecture: bool,
) -> ConversationStage:
    """Promote to QUALIFY for architecture deliverable when context is sufficient."""
    if not deferred_architecture:
        return meta.stage_reached
    if snapshot.hypothesis_status == "conflicted":
        return meta.stage_reached
    from app.advisor.orchestrator.tool_gating import has_minimum_discovery_context

    if has_minimum_discovery_context(meta) or bool(meta.data_context):
        idx = max(STAGE_ORDER.get(meta.stage_reached, 0), STAGE_ORDER["QUALIFY"])
        for stage, order in STAGE_ORDER.items():
            if order == idx:
                return stage
    return meta.stage_reached
