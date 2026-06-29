"""Deterministic execution router — mode, tools, confidence gates."""

from __future__ import annotations

from app.advisor.constants import (
    PRODUCT_KEYWORDS,
    RAG_TOOLS,
    TOOL_CONFIDENCE_THRESHOLD,
)
from app.advisor.orchestrator.intent_classifier import (
    IntentResult,
    classify_intent,
    intent_is_explicit_solution_request,
)
from app.advisor.orchestrator.product_fit_mapper import map_product_fit
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth
from app.advisor.pipeline.mode_selector import (
    apply_progression_gates,
    execution_to_conversation_mode,
    select_execution_mode,
)
from app.advisor.pipeline.tool_planner import (
    apply_tool_gates,
    plan_tool,
    rag_bypass_if_needed,
)
from app.advisor.orchestrator.tool_gating import detect_deferred_deliverable_request
from app.advisor.pipeline.conversation_planner import TurnPlan
from app.advisor.types import (
    ExecutionMode,
    HypothesisSnapshot,
    ModeResolution,
    ProductFitDecision,
    ReadinessFlags,
    RouterDecisionRecord,
    RouterOutput,
    SessionMetadata,
    ToolInvocationPlan,
)


def _rag_required(intent: IntentResult, message: str, fit: ProductFitDecision) -> bool:
    lower = message.lower()
    if intent.intent in ("product_comparison", "concept_explanation"):
        return True
    if any(pid in lower for kw in PRODUCT_KEYWORDS.values() for pid in kw):
        return True
    if fit.catalog_product_fit or fit.solution_category == "custom_solutions":
        return True
    if "boolmind" in lower:
        return True
    return False


def _derive_evidence_score(snapshot: HypothesisSnapshot) -> float:
    return snapshot.overall_confidence


def _derive_routing_confidence_advisory(
    intent: IntentResult, snapshot: HypothesisSnapshot
) -> float:
    """Advisory only — must not influence execution mode."""
    base = snapshot.overall_confidence
    hyp_conf = max(snapshot.confidence_scores.values(), default=0.5)
    raw = min(intent.confidence, hyp_conf if hyp_conf > 0 else intent.confidence, base)
    if len(snapshot.unresolved_unknowns) >= 3:
        raw *= 0.85
    return raw


def resolve_mode_conflict(
    execution_mode: ExecutionMode,
    internal_mode: str,
    intent: str,
) -> tuple[list[str], ModeResolution]:
    trace: list[str] = []
    strip: list[str] = []
    if internal_mode == "recommend" and execution_mode == "DIAGNOSE":
        strip.extend(["recommendation", "mode_prompt_suffix"])
        trace.append("stripped=recommendation_block")
    if intent == "product_comparison" and execution_mode == "DISCOVERY":
        strip.append("product_compare_nudge")
        trace.append("stripped=product_compare_nudge")
    kind = "direct" if not strip else "blocks_stripped"
    return strip, ModeResolution(kind=kind, trace=trace)


def derive_router_output(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    message: str,
    readiness: ReadinessFlags,
    *,
    product_fit: ProductFitDecision | None = None,
    active_product: str | None = None,
    history_texts: list[str] | None = None,
    turn_plan: TurnPlan | None = None,
) -> RouterOutput:
    history = history_texts or []
    fit = product_fit or map_product_fit(meta, message, history)
    intent = classify_intent(message)
    deferred_tool = detect_deferred_deliverable_request(message)

    legacy_fit = fit.catalog_product_fit or (
        fit.solution_category if fit.solution_category not in (None, "undecided") else None
    )

    mode, mode_reasons = select_execution_mode(
        meta, snapshot, intent, deferred_tool, message, history
    )
    mode, progression_gates = apply_progression_gates(mode, snapshot, intent)
    gates: list[str] = [*mode_reasons, *progression_gates]

    depth = DiagnosticDepth(score=meta.diagnostic_depth)

    deferred = detect_deferred_deliverable_request(message)
    bypass_depth_gates = intent_is_explicit_solution_request(intent) or (
        deferred == "generate_architecture_proposal" and "generate" in message.lower()
    )

    if depth.score < 25 and mode in ("DIAGNOSE", "SALES", "ARCHITECTURE"):
        if not bypass_depth_gates:
            gates.append(f"diagnostic_depth={depth.score}<25->DISCOVERY")
            mode = "DISCOVERY"

    if depth.solution_gated and mode in ("SALES", "ARCHITECTURE"):
        if not bypass_depth_gates:
            gates.append(f"diagnostic_depth={depth.score}<60->{mode}->DISCOVERY")
            mode = "DISCOVERY"

    if turn_plan and turn_plan.force_discovery_mode and mode not in ("DISCOVERY", "RAG_ONLY"):
        gates.append("planner:force_discovery_mode")
        mode = "DISCOVERY"

    rag_req = _rag_required(intent, message, fit)
    routing_confidence = _derive_routing_confidence_advisory(intent, snapshot)
    tool_confidence = routing_confidence
    evidence_score = _derive_evidence_score(snapshot)

    internal_mode = execution_to_conversation_mode(mode)  # type: ignore[assignment]

    strip_ids, resolution = resolve_mode_conflict(mode, internal_mode, intent.intent)

    tool_name, tool_reason, tool_plan, plan_gates = plan_tool(
        mode,
        intent,
        rag_req,
        message,
        meta,
        fit,
        readiness,
        active_product,
        tool_confidence=tool_confidence,
        legacy_fit=legacy_fit,
    )
    gates.extend(plan_gates)

    if depth.lead_capture_gated and tool_plan and tool_plan.tool_name == "crm_create_lead":
        gates.append(f"diagnostic_depth={depth.score}<40->crm_suppressed")
        tool_name, tool_reason, tool_plan = None, None, None

    tool_name, tool_reason, tool_plan, tool_gates = apply_tool_gates(
        tool_name,
        tool_reason,
        tool_plan,
        readiness,
        legacy_fit,
        tool_confidence=tool_confidence,
        execution_mode=mode,
    )
    gates.extend(tool_gates)

    tool_name, tool_reason, tool_plan = rag_bypass_if_needed(
        rag_req, tool_plan, intent.intent, message, meta, fit, active_product
    )

    if tool_plan and tool_plan.tool_name not in RAG_TOOLS:
        if tool_confidence < TOOL_CONFIDENCE_THRESHOLD:
            gates.append(
                f"routing_confidence_advisory:{routing_confidence:.2f}->ignored_for_mode"
            )

    required = [tool_plan.tool_name] if tool_plan else []

    record = RouterDecisionRecord(
        intent=intent.intent,
        intent_confidence=intent.confidence,
        routing_confidence=routing_confidence,
        tool_confidence=tool_confidence,
        execution_mode=mode,
        internal_mode=internal_mode,  # type: ignore[arg-type]
        catalog_product_fit=fit.catalog_product_fit,
        catalog_reasons=fit.catalog_reasons,
        solution_category=fit.solution_category,
        solution_reasons=fit.solution_reasons,
        rag_required=rag_req,
        tool_selected=tool_name,
        tool_reason=tool_reason,
        tool_plan_arguments=tool_plan.arguments if tool_plan else None,
        confidence_gates_applied=gates,
        resolution_trace=resolution.trace,
        evidence_score=evidence_score,
        mode_reasons=mode_reasons,
    )

    return RouterOutput(
        intent=intent.intent,
        mode=mode,
        required_tools=required,
        tool_plan=tool_plan,
        rag_required=rag_req,
        routing_confidence=routing_confidence,
        tool_confidence=tool_confidence,
        internal_mode=internal_mode,  # type: ignore[assignment]
        resolution=resolution,
        strip_block_ids=strip_ids,
        product_fit=fit,
        decision_record=record,
    )
