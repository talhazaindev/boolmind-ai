"""Tests for outcome framing block in prompt composition."""

from __future__ import annotations

from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.orchestrator.prompt_composition import (
    MODE_PROMPT_COMPOSITION,
    assemble_execution_prompt,
    build_outcome_framing_block,
)
from app.advisor.pipeline.conversation_planner import TurnPlan
from app.advisor.types import (
    BusinessMemorySnapshot,
    HypothesisSnapshot,
    ProductFitDecision,
    RouterOutput,
    SessionMetadata,
    TurnContext,
)

_CRM_ARCHETYPE = BusinessArchetype(
    id="lead_leakage",
    name="Lead Leakage",
    symptoms=["we lose track of leads"],
    root_cause="No CRM or manual spreadsheet tracking",
    it_lever="crm_implementation",
    boolmind_services=["crm_customisation"],
    discriminating_question="When a new lead comes in today, what happens first?",
    outcome_frame="Recover lost leads with automated follow-up.",
)


def _ctx(
    *,
    mode: str = "SALES",
    allow_solution_hint: bool = True,
    force_discovery_mode: bool = False,
    matched_archetypes: list[BusinessArchetype] | None = None,
) -> TurnContext:
    return TurnContext(
        session_id="s1",
        message="We lose track of leads constantly.",
        history_texts=(),
        frozen_meta=SessionMetadata(),
        extracted_meta=SessionMetadata(),
        snapshot=HypothesisSnapshot(),
        business_memory=BusinessMemorySnapshot(),
        product_fit_decision=ProductFitDecision(),
        router_output=RouterOutput(intent="general", mode=mode),  # type: ignore[arg-type]
        turn_plan=TurnPlan(
            this_turn_priority="solution_readiness",
            allow_solution_hint=allow_solution_hint,
            force_discovery_mode=force_discovery_mode,
        ),
        matched_archetypes=matched_archetypes or [_CRM_ARCHETYPE],
    )


def test_mode_composition_includes_outcome_framing_for_diagnose_and_sales() -> None:
    assert "outcome_framing" in MODE_PROMPT_COMPOSITION["DIAGNOSE"]
    assert "outcome_framing" in MODE_PROMPT_COMPOSITION["SALES"]
    assert "outcome_framing" not in MODE_PROMPT_COMPOSITION["DISCOVERY"]


def test_build_outcome_framing_block_includes_language_constraints() -> None:
    block = build_outcome_framing_block([_CRM_ARCHETYPE], TurnPlan(
        this_turn_priority="solution_readiness",
        allow_solution_hint=True,
    ))
    assert "LANGUAGE CONSTRAINTS FOR THIS RESPONSE" in block
    assert "Pain frame" in block
    assert "Solution frame" in block
    assert "Avoid these IT terms" in block
    assert "CRM" in block
    assert "never lose track of a customer again" in block


def test_build_outcome_framing_block_empty_without_solution_hint() -> None:
    block = build_outcome_framing_block(
        [_CRM_ARCHETYPE],
        TurnPlan(this_turn_priority="confirm_root_cause", allow_solution_hint=False),
    )
    assert block == ""


def test_build_outcome_framing_block_empty_when_force_discovery_mode() -> None:
    block = build_outcome_framing_block(
        [_CRM_ARCHETYPE],
        TurnPlan(
            this_turn_priority="confirm_root_cause",
            allow_solution_hint=True,
            force_discovery_mode=True,
        ),
    )
    assert block == ""


def test_build_outcome_framing_block_empty_for_unknown_lever() -> None:
    unknown = BusinessArchetype(
        id="unknown",
        name="Unknown",
        symptoms=["symptom"],
        root_cause="cause",
        it_lever="nonexistent_lever",
        boolmind_services=["web_development"],
        discriminating_question="What is the main issue?",
        outcome_frame="Better outcomes.",
    )
    block = build_outcome_framing_block(
        [unknown],
        TurnPlan(this_turn_priority="solution_readiness", allow_solution_hint=True),
    )
    assert block == ""


def test_assembled_sales_prompt_includes_outcome_framing_when_allowed() -> None:
    prompt = assemble_execution_prompt(_ctx(mode="SALES", allow_solution_hint=True))
    assert "LANGUAGE CONSTRAINTS FOR THIS RESPONSE" in prompt
    assert "falls through the cracks" in prompt


def test_assembled_discovery_prompt_omits_outcome_framing() -> None:
    prompt = assemble_execution_prompt(_ctx(mode="DISCOVERY", allow_solution_hint=True))
    assert "LANGUAGE CONSTRAINTS FOR THIS RESPONSE" not in prompt


def test_assembled_diagnose_prompt_omits_outcome_framing_without_solution_hint() -> None:
    prompt = assemble_execution_prompt(_ctx(mode="DIAGNOSE", allow_solution_hint=False))
    assert "LANGUAGE CONSTRAINTS FOR THIS RESPONSE" not in prompt
