"""L8 — tool orchestration with eligibility matrix."""

from __future__ import annotations

import re

from app.advisor.constants import DELIVERABLE_TOOLS, RAG_TOOLS, TOOL_CONFIDENCE_THRESHOLD
from app.advisor.orchestrator.intent_classifier import IntentResult
from app.advisor.orchestrator.rag_query_builder import (
    build_bi_rag_spec,
    build_product_compare_args,
    build_rag_spec,
)
from app.advisor.orchestrator.tool_gating import (
    detect_deferred_deliverable_request,
    is_tool_allowed,
)
from app.advisor.types import (
    ExecutionMode,
    ProductFitDecision,
    ReadinessFlags,
    SessionMetadata,
    ToolInvocationPlan,
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _build_deferred_plan(
    deferred_tool: str,
    message: str,
    meta: SessionMetadata,
    fit: ProductFitDecision,
    active_product: str | None,
) -> ToolInvocationPlan | None:
    if deferred_tool == "generate_architecture_proposal":
        return ToolInvocationPlan(
            tool_name=deferred_tool,
            arguments={
                "requirements": message[:500],
                "product_id": fit.catalog_product_fit or "custom_solutions",
            },
        )
    if deferred_tool == "product_tour":
        return ToolInvocationPlan(
            tool_name=deferred_tool,
            arguments={
                "product_id": fit.catalog_product_fit or active_product or "retify",
            },
        )
    if deferred_tool == "generate_fidp":
        return ToolInvocationPlan(
            tool_name=deferred_tool,
            arguments={
                "requirements": message[:500],
                "product_id": fit.catalog_product_fit or "custom_solutions",
            },
        )
    if deferred_tool == "calendar_get_slots":
        return ToolInvocationPlan(tool_name=deferred_tool, arguments={})
    if deferred_tool in ("calendar_book_slot", "send_meeting_invite"):
        return ToolInvocationPlan(
            tool_name=deferred_tool,
            arguments={"message": message[:300]},
        )
    return None


def _detect_crm_intent(message: str, meta: SessionMetadata) -> bool:
    lower = message.lower()
    has_email = bool(_EMAIL_RE.search(message) or meta.collected_email)
    lead_signals = ("follow up", "contact me", "my email", "my name is", "reach out")
    return has_email and any(sig in lower for sig in lead_signals)


def plan_tool(
    mode: ExecutionMode,
    intent: IntentResult,
    rag_required: bool,
    message: str,
    meta: SessionMetadata,
    fit: ProductFitDecision,
    readiness: ReadinessFlags,
    active_product: str | None,
    *,
    tool_confidence: float,
    legacy_fit: str | None,
) -> tuple[str | None, str | None, ToolInvocationPlan | None, list[str]]:
    """Select at most one pre-flight tool. Returns (name, reason, plan, gates)."""
    gates: list[str] = []
    deferred_tool = detect_deferred_deliverable_request(message)

    if intent.intent == "product_comparison":
        return (
            "product_compare",
            "product_comparison intent; self-grounding compare",
            ToolInvocationPlan(
                tool_name="product_compare",
                arguments=build_product_compare_args(meta, message),
            ),
            gates,
        )

    if deferred_tool and mode in ("ARCHITECTURE", "SALES", "DIAGNOSE"):
        if deferred_tool == "generate_architecture_proposal" and mode == "ARCHITECTURE":
            plan = _build_deferred_plan(deferred_tool, message, meta, fit, active_product)
            if plan:
                return deferred_tool, f"deferred deliverable: {deferred_tool}", plan, gates
        elif deferred_tool != "generate_architecture_proposal" and mode in ("ARCHITECTURE", "SALES"):
            plan = _build_deferred_plan(deferred_tool, message, meta, fit, active_product)
            if plan:
                return deferred_tool, f"deferred deliverable: {deferred_tool}", plan, gates

    if _detect_crm_intent(message, meta) and readiness.lead_capture:
        email_match = _EMAIL_RE.search(message)
        email = meta.collected_email or (email_match.group(0) if email_match else None)
        if email:
            return (
                "crm_create_lead",
                "lead capture readiness + contact in message",
                ToolInvocationPlan(
                    tool_name="crm_create_lead",
                    arguments={
                        "email": email,
                        "name": meta.visitor_name or "Visitor",
                        "product_id": fit.catalog_product_fit or legacy_fit or "custom_solutions",
                        "products_discussed": meta.products_discussed or [],
                    },
                ),
                gates,
            )

    if mode in ("DISCOVERY", "DIAGNOSE") and fit.solution_category == "custom_solutions":
        return (
            "rag_query",
            "business intelligence patterns for discovery",
            ToolInvocationPlan(
                tool_name="rag_query",
                arguments=build_bi_rag_spec(meta, message),
            ),
            gates,
        )

    if rag_required:
        return (
            "rag_query",
            "Boolmind capability / factual lookup required",
            ToolInvocationPlan(
                tool_name="rag_query",
                arguments=build_rag_spec(intent.intent, message, meta, fit, active_product),
            ),
            gates,
        )

    return None, None, None, gates


def apply_tool_gates(
    tool_name: str | None,
    tool_reason: str | None,
    tool_plan: ToolInvocationPlan | None,
    readiness: ReadinessFlags,
    legacy_fit: str | None,
    *,
    tool_confidence: float,
    execution_mode: ExecutionMode | None = None,
) -> tuple[str | None, str | None, ToolInvocationPlan | None, list[str]]:
    """Gate deliverables by confidence and readiness — never gate RAG tools."""
    gates: list[str] = []
    if tool_plan is None:
        return tool_name, tool_reason, tool_plan, gates

    if tool_plan.tool_name in DELIVERABLE_TOOLS:
        exempt_architecture = (
            tool_plan.tool_name == "generate_architecture_proposal"
            and execution_mode == "ARCHITECTURE"
        )
        if not exempt_architecture and tool_confidence < TOOL_CONFIDENCE_THRESHOLD:
            gates.append(f"tool_confidence:{tool_confidence:.2f}->clear_deliverable")
            return None, None, None, gates
        if not is_tool_allowed(tool_plan.tool_name, readiness, product_fit=legacy_fit):
            gates.append(f"gated:{tool_plan.tool_name}")
            return None, "readiness gated", None, gates

    return tool_name, tool_reason, tool_plan, gates


def rag_bypass_if_needed(
    rag_required: bool,
    tool_plan: ToolInvocationPlan | None,
    intent: str,
    message: str,
    meta: SessionMetadata,
    fit: ProductFitDecision,
    active_product: str | None,
) -> tuple[str | None, str | None, ToolInvocationPlan | None]:
    if rag_required and (tool_plan is None or tool_plan.tool_name not in RAG_TOOLS):
        return (
            "rag_query",
            "rag_required bypass",
            ToolInvocationPlan(
                tool_name="rag_query",
                arguments=build_rag_spec(intent, message, meta, fit, active_product),
            ),
        )
    return (
        tool_plan.tool_name if tool_plan else None,
        "rag_required bypass" if tool_plan else None,
        tool_plan,
    )
