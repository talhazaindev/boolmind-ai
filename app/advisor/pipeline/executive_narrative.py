"""Executive narrative — deterministic slots, LLM rewrites prose only."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessSystemsState,
    ExecutiveNarrative,
    NarrativeState,
    RecommendationReadiness,
)


def build_narrative_state(
    bss: BusinessSystemsState,
) -> NarrativeState:
    primary_driver = bss.economic_drivers[0] if bss.economic_drivers else "revenue_growth"
    pattern_label = bss.pattern_matches[0].pattern.label if bss.pattern_matches else None
    top_cause = ""
    top_conf = 0.0
    top_strength = "speculated"
    competing = None
    if bss.confidence.root_causes:
        top_cause = bss.confidence.root_causes[0].label
        top_conf = bss.confidence.root_causes[0].confidence
        top_strength = bss.confidence.root_causes[0].evidence_strength
        if len(bss.confidence.root_causes) > 1:
            competing = bss.confidence.root_causes[1].label

    model_summary = ", ".join(bss.business_model.revenue_mechanisms) or "operating model emerging"
    if bss.business_model.cost_structure:
        model_summary += f"; costs: {', '.join(bss.business_model.cost_structure[:2])}"

    stakeholder_conflict = None
    if bss.incentive_conflicts:
        c = bss.incentive_conflicts[0]
        stakeholder_conflict = f"{c.stakeholder_a} vs {c.stakeholder_b}: {c.conflict_reason}"

    constraint_summary = None
    if bss.constraint_profile.constraints:
        constraint_summary = "; ".join(
            f"{c.type.lower()}: {c.description}" for c in bss.constraint_profile.constraints[:3]
        )

    step_type = "clarifying_question"
    step_slot = bss.recommended_question or ""
    if bss.readiness.ready and bss.intervention_candidates:
        step_type = "intervention"
        step_slot = bss.intervention_candidates[0].description
    elif bss.readiness.blocking_reasons:
        if any("constraint" in b for b in bss.readiness.blocking_reasons):
            step_type = "constraint_question"
        elif any("intervention_evidence" in b or "missing" in b for b in bss.readiness.blocking_reasons):
            step_type = "evidence_question"

    opp_cost = bss.opportunity_ranking[0].opportunity_cost if bss.opportunity_ranking else 0.0

    return NarrativeState(
        primary_driver=primary_driver,
        business_model_summary=model_summary,
        pattern_label=pattern_label,
        top_cause=top_cause,
        top_cause_confidence=top_conf,
        top_cause_evidence_strength=top_strength,
        competing_cause=competing,
        top_issue_opportunity_cost=opp_cost,
        stakeholder_conflict=stakeholder_conflict,
        maturity_stage=bss.maturity.stage,
        constraint_summary=constraint_summary,
        value_chain_active=bss.value_chain.active,
        recommended_next_step_type=step_type,
        recommended_next_step_slot=step_slot,
    )


def render_prose_template(state: NarrativeState) -> str:
    parts: list[str] = []
    if state.pattern_label:
        parts.append(f"The pattern resembles {state.pattern_label}.")
    if state.business_model_summary:
        parts.append(f"Revenue appears driven by {state.business_model_summary}.")
    if state.top_cause:
        qualifier = (
            "you mentioned"
            if state.top_cause_evidence_strength == "observed"
            else "the evidence suggests"
        )
        parts.append(
            f"{qualifier.capitalize()} the strongest pressure may be {state.top_cause} "
            f"(confidence {state.top_cause_confidence:.0%})."
        )
    if state.competing_cause:
        parts.append(f"{state.competing_cause} remains a plausible alternative.")
    if state.stakeholder_conflict:
        parts.append(f"There may also be a stakeholder tension: {state.stakeholder_conflict}.")
    if state.recommended_next_step_type == "intervention" and state.recommended_next_step_slot:
        parts.append(f"If validated, a leading option would be: {state.recommended_next_step_slot}.")
    elif state.recommended_next_step_slot:
        parts.append(state.recommended_next_step_slot)
    return " ".join(parts) if parts else "Tell me more about what is hurting most right now."


def render_narrative_prompt_block(state: dict[str, object] | None) -> str:
    """Format executive narrative slots for the LLM system prompt."""
    if not state:
        return ""
    lines = ["EXECUTIVE_NARRATIVE (deterministic slots — do not invent beyond these):"]
    for key in (
        "pattern_label",
        "business_model_summary",
        "top_cause",
        "top_cause_confidence",
        "top_cause_evidence_strength",
        "competing_cause",
        "top_issue_opportunity_cost",
        "stakeholder_conflict",
        "maturity_stage",
        "constraint_summary",
        "value_chain_active",
        "recommended_next_step_type",
        "recommended_next_step_slot",
    ):
        val = state.get(key)
        if val is not None and val != "" and val is not False:
            lines.append(f"{key}={val}")
    if len(lines) == 1:
        return ""
    lines.append(
        "Rewrite these slots in natural consultant prose only. "
        "Do not add facts absent from slots."
    )
    return "\n".join(lines)


def validate_llm_prose(prose: str, state: NarrativeState) -> bool:
    """Reject prose that introduces major facts absent from slots."""
    if not prose.strip():
        return False
    if state.top_cause and state.top_cause.lower()[:20] not in prose.lower():
        if state.top_cause_evidence_strength == "observed":
            return False
    forbidden = ("hypothesis 1", "hypothesis 2", "hypothesis 3")
    return not any(f in prose.lower() for f in forbidden)


def generate_executive_narrative(bss: BusinessSystemsState) -> ExecutiveNarrative:
    state = build_narrative_state(bss)
    prose = render_prose_template(state)
    return ExecutiveNarrative(narrative_state=state, prose=prose)
