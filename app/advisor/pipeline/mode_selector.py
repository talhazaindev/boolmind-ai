"""L7 — execution mode selection (single authority)."""

from __future__ import annotations

from app.advisor.constants import DIAGNOSIS_CONFIDENCE_THRESHOLD
from app.advisor.orchestrator.conversation_progression import discovery_exit_met
from app.advisor.orchestrator.diagnosis_router import should_diagnose
from app.advisor.orchestrator.intent_classifier import IntentResult
from app.advisor.orchestrator.tool_gating import has_minimum_discovery_context
from app.advisor.types import ExecutionMode, HypothesisSnapshot, SessionMetadata

_IMMUNE_MODES: frozenset[ExecutionMode] = frozenset({
    "RAG_ONLY",
    "ARCHITECTURE",
})


def _diagnosis_allowed(snapshot: HypothesisSnapshot, meta: SessionMetadata) -> bool:
    """Block premature diagnosis until evidence threshold and discovery depth met."""
    if snapshot.overall_confidence < DIAGNOSIS_CONFIDENCE_THRESHOLD:
        return False
    has_scale = bool(snapshot.scale_indicators or meta.data_context)
    if has_scale and meta.message_count < 3:
        return False
    return True


def select_execution_mode(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    intent: IntentResult,
    deferred_tool: str | None,
    message: str,
    history: list[str],
) -> tuple[ExecutionMode, list[str]]:
    """State-machine mode selection — confidence does not influence mode."""
    reasons: list[str] = []

    if snapshot.hypothesis_status == "conflicted" or meta.conflict_hold:
        return "DISCOVERY", ["conflict_hold->DISCOVERY"]

    if intent.intent == "concept_explanation":
        return "RAG_ONLY", ["intent=concept_explanation"]

    if intent.intent == "product_comparison":
        return "RAG_ONLY", ["intent=product_comparison"]

    if deferred_tool == "generate_architecture_proposal":
        if has_minimum_discovery_context(meta) or meta.data_context:
            return "ARCHITECTURE", ["deferred_architecture+minimum_context"]
        reasons.append("architecture_deferred_insufficient_context")

    if intent.intent == "advice_request" and not snapshot.solutioning_allowed:
        if _diagnosis_allowed(snapshot, meta):
            return "DIAGNOSE", ["advice_request+solutioning_blocked+confidence_met"]
        return "DISCOVERY", ["advice_request+insufficient_confidence"]

    stage = snapshot.conversation_stage

    if stage in ("HYPOTHESIS_VALIDATION", "SOLUTION_ALIGNMENT") and snapshot.solutioning_allowed:
        return "SALES", ["stage=SOLUTION_ALIGNMENT", "solutioning_allowed"]

    if should_diagnose(meta, message, history) or stage in (
        "BOTTLENECK_ISOLATION",
        "HYPOTHESIS_VALIDATION",
    ):
        if stage in ("HYPOTHESIS_VALIDATION", "SOLUTION_ALIGNMENT") and snapshot.solutioning_allowed:
            return "SALES", ["diagnose_exit+solutioning_allowed"]
        if _diagnosis_allowed(snapshot, meta):
            return "DIAGNOSE", [f"stage={stage}", "should_diagnose", "confidence_met"]
        return "DISCOVERY", [f"stage={stage}", "diagnosis_deferred_low_confidence"]

    if discovery_exit_met(meta, snapshot) and stage != "DISCOVERY":
        if _diagnosis_allowed(snapshot, meta):
            return "DIAGNOSE", ["discovery_exit_met->DIAGNOSE"]
        return "DISCOVERY", ["discovery_exit_met+confidence_deferred"]

    if deferred_tool and deferred_tool != "generate_architecture_proposal":
        return "SALES", [f"deferred_deliverable={deferred_tool}"]

    return "DISCOVERY", reasons or ["default_discovery"]


def apply_progression_gates(
    mode: ExecutionMode,
    snapshot: HypothesisSnapshot,
    intent: IntentResult,
) -> tuple[ExecutionMode, list[str]]:
    """Hard gates that can only restrict SALES/ARCHITECTURE — never downgrade immune modes."""
    gates: list[str] = []
    if mode in _IMMUNE_MODES:
        if mode == "SALES" and not snapshot.solutioning_allowed:
            gates.append("solutioning_blocked->DIAGNOSE")
            return "DIAGNOSE", gates
        return mode, gates

    if mode == "SALES" and not snapshot.solutioning_allowed:
        gates.append("solutioning_blocked->DIAGNOSE")
        return "DIAGNOSE", gates

    if intent.intent == "advice_request" and not snapshot.solutioning_allowed:
        if mode in ("SALES", "ARCHITECTURE"):
            gates.append("advice_premature->DIAGNOSE")
            return "DIAGNOSE", gates

    if snapshot.conversation_stage in (
        "DISCOVERY",
        "CONSTRAINT_MAPPING",
        "BOTTLENECK_ISOLATION",
    ) and mode == "SALES":
        gates.append("stage_blocks_sales->DIAGNOSE")
        return "DIAGNOSE", gates

    return mode, gates


def execution_to_conversation_mode(mode: ExecutionMode) -> str:
    """Backward-compatible internal mode label for SSE."""
    mapping = {
        "DISCOVERY": "discover",
        "DIAGNOSE": "diagnose",
        "SALES": "advise",
        "ARCHITECTURE": "deliver",
        "RAG_ONLY": "discover",
    }
    return mapping.get(mode, "discover")


def is_mode_immune_to_confidence_downgrade(mode: ExecutionMode) -> bool:
    return mode in _IMMUNE_MODES
