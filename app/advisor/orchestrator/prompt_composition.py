"""Frozen prompt composition per ExecutionMode."""

from __future__ import annotations

from typing import Final

from app.advisor.orchestrator.business_memory import render_business_memory_block
from app.advisor.orchestrator.response_quality import quality_hint_block
from app.advisor.orchestrator.system_prompt import SECTION_A, SECTION_G
from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.knowledge.translation_map import get_outcome_framing
from app.advisor.pipeline.conversation_planner import TurnPlan
from app.advisor.pipeline.executive_narrative import render_narrative_prompt_block
from app.advisor.types import DiagnoseDepth, ExecutionMode, HypothesisSnapshot, TurnContext

PromptBlockId = str

MODE_PROMPT_COMPOSITION: Final[dict[ExecutionMode, tuple[PromptBlockId, ...]]] = {
    "DISCOVERY": (
        "identity",
        "mode",
        "business_memory",
        "hypothesis",
        "narrative",
        "turn_value",
        "narrator",
        "grounding",
        "stage_rules",
    ),
    "DIAGNOSE": (
        "identity",
        "mode",
        "business_memory",
        "hypothesis",
        "narrative",
        "turn_value",
        "outcome_framing",
        "narrator",
        "grounding",
    ),
    "SALES": (
        "identity",
        "mode",
        "business_memory",
        "hypothesis",
        "narrative",
        "outcome_framing",
        "grounding",
        "stage_rules",
    ),
    "ARCHITECTURE": ("identity", "mode", "business_memory", "deliverable"),
    "RAG_ONLY": ("identity", "mode", "grounding"),
}

_FACT_GROUNDING_POLICY = (
    "FACT-GROUNDING (mandatory):\n"
    "- Only assert facts the user explicitly stated or that appear in CONVERSATION_STATE.\n"
    "- NEVER say 'the backlog you described' unless backlog is in CONVERSATION_STATE.\n"
    "- NEVER invent ERP issues, scheduling problems, or backlogs the user did not mention.\n"
    "- HYPOTHESIS_STATE is internal — never present hypotheses as confirmed findings.\n"
    "- Until overall_confidence >= 0.75: use hedging (may indicate, could suggest, "
    "one possibility, potential contributor).\n"
    "- DISALLOWED unless confidence threshold met: clear bottleneck, root cause is, "
    "primary bottleneck is, you're seeing, this confirms, this aligns with."
)

_DISCOVERY_LANGUAGE = (
    "DISCOVERY LANGUAGE: Do not diagnose. Acknowledge user-stated facts only. "
    "Offer possible contributors with hedging — never as confirmed root cause."
)

_FEW_SHOT_LENDING = (
    "REFERENCE DIALOGUE (lending — tone only, do not copy verbatim):\n"
    "User: approval times went from 3 days to 9 days.\n"
    "Advisor: That kind of slowdown usually shows up in document gathering, "
    "underwriting analysis, or compliance handoffs. Which of those feels worst right now?\n"
    "User: 220 applications per day, manual docs, 600 backlog, automation failed.\n"
    "Advisor: Three days to nine is a serious slip, and a 600-application backlog at "
    "your volume is roughly three days of queue on its own."
)

_FEW_SHOT_LOGISTICS = (
    "REFERENCE DIALOGUE (logistics — tone only):\n"
    "User: drivers wait 30-60 minutes during peak.\n"
    "Advisor: Driver wait at peak usually traces to planning lag or assignment rules, "
    "not driver capacity. When dispatch slips, what breaks first — route planning or "
    "who gets the next job?"
)

_MODE_CONSTRAINTS: dict[ExecutionMode, str] = {
    "DISCOVERY": (
        "EXECUTION MODE: DISCOVERY — Clarify and build a shared working picture. "
        "After turn 2 you MUST deliver user value each turn (see TURN VALUE block when present). "
        "Do NOT propose final solutions, pricing, CRM, or booking. "
        "Tentative drafts and workflow sketches are allowed when TURN VALUE is present — "
        "always label them as drafts awaiting user confirmation. "
        "Acknowledge the user's situation in one sentence using ONLY their stated facts. "
        "Do NOT ask questions contradicted by KNOWN FACTS or CONVERSATION_STATE. "
        "Do NOT use numbered lists or checklist-style sub-questions. "
        "NEXT_QUESTION will be appended — do NOT ask any question in your body."
    ),
    "DIAGNOSE": (
        "EXECUTION MODE: DIAGNOSE — Natural consultant diagnosis only. "
        "Open with one empathetic acknowledgment of user-stated facts. "
        "Follow with 2-3 sentences of insight in plain language — hedge unless confidence is high. "
        "No labels (Observation/Evidence/Inference). No numbered lists. "
        "Do NOT pitch Boolmind products unless SALES mode. "
        "Do NOT ask questions already answered in KNOWN FACTS. "
        "NEXT_QUESTION will be appended — do NOT ask any question in your body."
    ),
    "SALES": (
        "EXECUTION MODE: SALES — Map Boolmind solution to validated problem. "
        "Only when solutioning_allowed. No aggressive lead capture unless readiness allows."
    ),
    "ARCHITECTURE": (
        "EXECUTION MODE: ARCHITECTURE — System design only. No marketing. "
        "Use DELIVERABLE block if present."
    ),
    "RAG_ONLY": (
        "EXECUTION MODE: RAG_ONLY — Answer factually from GROUNDING only. "
        "Concise, direct, technically credible."
    ),
}

_DIAGNOSE_FORMAT: dict[DiagnoseDepth, str] = {
    "early": (
        "DIAGNOSE FORMAT: empathetic opener + 2-3 sentences of operational insight. "
        "No solutioning until solutioning_allowed."
    ),
    "mid": (
        "DIAGNOSE FORMAT: leading hypothesis in plain language + supporting fact + "
        "tradeoff of a wrong fix. No labels."
    ),
    "late": (
        "DIAGNOSE FORMAT: concise inference + tradeoff, max 3 short sentences. No labels."
    ),
}


def build_execution_mode_block(
    mode: ExecutionMode,
    snapshot: HypothesisSnapshot,
    *,
    quality_hint: bool = False,
    turn_plan: TurnPlan | None = None,
    matched_archetypes: list[BusinessArchetype] | None = None,
) -> str:
    parts = [_MODE_CONSTRAINTS[mode]]
    if mode in ("DISCOVERY", "DIAGNOSE"):
        parts.append(_FACT_GROUNDING_POLICY)
    if mode == "DISCOVERY":
        parts.append(_DISCOVERY_LANGUAGE)
    if snapshot.hypothesis_status == "conflicted" and snapshot.conflict_detail:
        parts.append(
            "CONFLICT DETECTED — Your body MUST acknowledge the contradiction and "
            f"ask for clarification. Use this framing: {snapshot.conflict_detail}"
        )
    if mode == "DIAGNOSE":
        parts.append(_DIAGNOSE_FORMAT[snapshot.diagnose_depth])
        if not snapshot.solutioning_allowed:
            parts.append(
                "SOLUTIONING FORBIDDEN: confirmed_bottlenecks < 2. "
                "Do NOT mention automation, custom solutions, or AI-driven tools."
            )
    if snapshot.required_question:
        parts.append(
            "Generate response BODY only. Do NOT include a closing question."
        )
    if quality_hint:
        parts.append(quality_hint_block())
    mode_block = "\n\n".join(parts)

    planner_instructions: list[str] = []
    if turn_plan and turn_plan.force_discovery_mode:
        planner_instructions.append(
            "You are in DIAGNOSTIC MODE. Do not propose solutions or mention specific services. "
            "Focus entirely on understanding the business problem more deeply."
        )
    if turn_plan and turn_plan.allow_case_reference and matched_archetypes:
        arch = matched_archetypes[0]
        if arch.case_hook:
            planner_instructions.append(
                f"You may briefly reference this proof point if relevant: {arch.case_hook}"
            )
    if turn_plan and turn_plan.allow_solution_hint:
        planner_instructions.append(
            "The problem is now well-understood. You may begin to orient toward solution direction, "
            "but do not pitch specific services yet — frame the intervention category first."
        )
    if planner_instructions:
        mode_block += "\n\nPLANNER GUIDANCE:\n" + "\n".join(planner_instructions)

    return mode_block


def _hypothesis_block(snapshot: HypothesisSnapshot, mode: ExecutionMode) -> str:
    lines = [
        f"business_model={snapshot.business_model}",
        f"vertical={snapshot.active_business_vertical or 'unknown'}",
        f"stage={snapshot.conversation_stage}",
        f"status={snapshot.hypothesis_status}",
        f"overall_confidence={snapshot.overall_confidence:.2f}",
        f"solutioning_allowed={snapshot.solutioning_allowed}",
        "NOTE: fields below are INTERNAL hypotheses — not confirmed facts for the user.",
    ]
    if snapshot.primary_bottleneck and (
        mode != "DISCOVERY" and snapshot.overall_confidence >= 0.75
    ):
        lines.append(f"primary_bottleneck={snapshot.primary_bottleneck}")
    elif snapshot.primary_bottleneck:
        lines.append(f"candidate_bottleneck={snapshot.primary_bottleneck}")
    if snapshot.resolved_unknowns:
        lines.append(f"resolved={','.join(snapshot.resolved_unknowns)}")
    if snapshot.unresolved_unknowns:
        lines.append(f"unresolved={','.join(snapshot.unresolved_unknowns)}")
    return "HYPOTHESIS_STATE:\n" + "\n".join(lines)


def _narrator_block(ctx: TurnContext) -> str:
    parts: list[str] = []
    if ctx.acknowledgment_hints:
        hints = "\n".join(f"- {h}" for h in ctx.acknowledgment_hints[:4])
        parts.append(f"NARRATOR HINTS (hedge unless confidence high):\n{hints}")
    if ctx.next_question:
        parts.append(f"NEXT_QUESTION (appended after your body — do NOT repeat):\n{ctx.next_question}")
    return "\n\n".join(parts)


def _narrative_block(ctx: TurnContext) -> str:
    return render_narrative_prompt_block(ctx.extracted_meta.executive_narrative or None)


def _stage_rules() -> str:
    return (
        "STAGE RULES: No lead capture until value delivered. "
        "No pricing. No phone or company size questions. "
        "One question per turn (appended). "
        "From turn 3 onward each reply must include insight or a draft sketch — not questions alone."
    )


def _turn_value_block(ctx: TurnContext) -> str:
    return (ctx.turn_value_block or "").strip()


def build_outcome_framing_block(
    matched_archetypes: list[BusinessArchetype] | None,
    turn_plan: TurnPlan | None,
) -> str:
    """
    Build an OUTCOME FRAMING block for the LLM prompt.

    Only injected when allow_solution_hint is True (and not force_discovery_mode).
    Block is listed in MODE_PROMPT_COMPOSITION for DIAGNOSE and SALES only.
    """
    if not matched_archetypes or turn_plan is None or not turn_plan.allow_solution_hint:
        return ""
    if turn_plan.force_discovery_mode:
        return ""

    primary = matched_archetypes[0]
    framing = get_outcome_framing(primary.it_lever)
    if not framing:
        return ""

    lines = [
        "LANGUAGE CONSTRAINTS FOR THIS RESPONSE:",
        f"Pain frame (use this to acknowledge the problem): {framing.get('pain_frame', '')}",
        f"Solution frame (use this to orient toward the fix): {framing.get('solution_frame', '')}",
        "Avoid these IT terms: " + ", ".join(framing.get("avoid_terms", [])),
        "Prefer these phrases instead: " + " | ".join(framing.get("use_instead", [])),
    ]
    return "\n".join(lines)


def _format_case_evidence(snippets: list[dict[str, str]]) -> str:
    lines = [
        "RELEVANT CASE EVIDENCE (use to build credibility, do not quote verbatim):",
    ]
    for snippet in snippets:
        lines.append(f"- {snippet.get('case_text', '')}")
        lines.append(f"  Outcome frame: {snippet.get('outcome_frame', '')}")
    return "\n".join(lines)


def _compose_grounding_block(ctx: TurnContext) -> str:
    parts: list[str] = []
    if ctx.router_output.mode == "RAG_ONLY" and ctx.grounding_block:
        parts.append(ctx.grounding_block.strip())
    turn_plan = ctx.turn_plan
    if ctx.case_evidence and turn_plan and turn_plan.allow_case_reference:
        parts.append(_format_case_evidence(ctx.case_evidence))
    return "\n\n".join(parts)


def assemble_execution_prompt(ctx: TurnContext) -> str:
    mode = ctx.router_output.mode
    composition = MODE_PROMPT_COMPOSITION[mode]
    strip = set(ctx.router_output.strip_block_ids)
    blocks: dict[PromptBlockId, str] = {
        "identity": SECTION_A,
        "mode": build_execution_mode_block(
            mode,
            ctx.snapshot,
            quality_hint=ctx.extracted_meta.quality_hint_next_turn,
            turn_plan=ctx.turn_plan,
            matched_archetypes=ctx.matched_archetypes or None,
        ),
        "business_memory": render_business_memory_block(
            ctx.business_memory, ctx.snapshot, ctx.context_graph
        ),
        "hypothesis": _hypothesis_block(ctx.snapshot, mode),
        "narrative": _narrative_block(ctx),
        "turn_value": _turn_value_block(ctx),
        "outcome_framing": build_outcome_framing_block(
            ctx.matched_archetypes or None,
            ctx.turn_plan,
        ),
        "narrator": _narrator_block(ctx),
        "stage_rules": _stage_rules(),
        "grounding": _compose_grounding_block(ctx),
        "deliverable": ctx.deliverable_block or "",
        "hard_rules": SECTION_G,
    }
    parts: list[str] = []
    for block_id in composition:
        if block_id in strip:
            continue
        text = blocks.get(block_id, "").strip()
        if text:
            parts.append(text)
    parts.append(
        "EXECUTOR RULE: Tools are pre-executed. Do NOT call tools. Synthesize only."
    )
    return "\n\n".join(parts)
