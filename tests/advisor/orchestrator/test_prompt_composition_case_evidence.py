"""Tests for case evidence grounding in prompt composition."""

from __future__ import annotations

from app.advisor.orchestrator.prompt_composition import (
    MODE_PROMPT_COMPOSITION,
    _compose_grounding_block,
    assemble_execution_prompt,
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

_CASE_SNIPPETS = [
    {
        "case_text": "A logistics company saved 120 hours/month with integrations.",
        "outcome_frame": "Eliminate manual re-entry for {vertical}",
        "archetype_name": "Manual Data Entry Tax",
    }
]


def _base_ctx(*, mode: str = "DIAGNOSE", allow_case: bool = True) -> TurnContext:
    return TurnContext(
        session_id="s1",
        message="We re-key data into three systems.",
        history_texts=(),
        frozen_meta=SessionMetadata(),
        extracted_meta=SessionMetadata(),
        snapshot=HypothesisSnapshot(),
        business_memory=BusinessMemorySnapshot(),
        product_fit_decision=ProductFitDecision(),
        router_output=RouterOutput(intent="general", mode=mode),  # type: ignore[arg-type]
        turn_plan=TurnPlan(
            this_turn_priority="confirm_root_cause",
            allow_case_reference=allow_case,
        ),
        case_evidence=_CASE_SNIPPETS if allow_case else [],
    )


def test_mode_composition_includes_grounding_for_discovery_diagnose_sales() -> None:
    assert "grounding" in MODE_PROMPT_COMPOSITION["DISCOVERY"]
    assert "grounding" in MODE_PROMPT_COMPOSITION["DIAGNOSE"]
    assert "grounding" in MODE_PROMPT_COMPOSITION["SALES"]


def test_compose_grounding_includes_case_evidence_when_allowed() -> None:
    block = _compose_grounding_block(_base_ctx(allow_case=True))
    assert "RELEVANT CASE EVIDENCE" in block
    assert "do not quote verbatim" in block
    assert _CASE_SNIPPETS[0]["case_text"] in block
    assert f"Outcome frame: {_CASE_SNIPPETS[0]['outcome_frame']}" in block


def test_compose_grounding_omits_case_evidence_when_not_allowed() -> None:
    block = _compose_grounding_block(_base_ctx(allow_case=False))
    assert block == ""


def test_compose_grounding_includes_rag_only_for_rag_only_mode() -> None:
    ctx = TurnContext(
        session_id="s1",
        message="What is Retify?",
        history_texts=(),
        frozen_meta=SessionMetadata(),
        extracted_meta=SessionMetadata(),
        snapshot=HypothesisSnapshot(),
        business_memory=BusinessMemorySnapshot(),
        product_fit_decision=ProductFitDecision(),
        router_output=RouterOutput(intent="product", mode="RAG_ONLY"),
        grounding_block="GROUNDING (authoritative):\n[1] Retify automates lending.",
        turn_plan=TurnPlan(this_turn_priority="answer", allow_case_reference=True),
        case_evidence=_CASE_SNIPPETS,
    )
    block = _compose_grounding_block(ctx)
    assert "GROUNDING (authoritative)" in block
    assert "RELEVANT CASE EVIDENCE" in block


def test_compose_grounding_case_only_for_diagnose_not_product_rag() -> None:
    ctx = TurnContext(
        session_id="s1",
        message="manual data entry",
        history_texts=(),
        frozen_meta=SessionMetadata(),
        extracted_meta=SessionMetadata(),
        snapshot=HypothesisSnapshot(),
        business_memory=BusinessMemorySnapshot(),
        product_fit_decision=ProductFitDecision(),
        router_output=RouterOutput(intent="general", mode="DIAGNOSE"),
        grounding_block="GROUNDING (authoritative):\n[1] BI pattern text.",
        turn_plan=TurnPlan(this_turn_priority="confirm_root_cause", allow_case_reference=True),
        case_evidence=_CASE_SNIPPETS,
    )
    block = _compose_grounding_block(ctx)
    assert "BI pattern text" not in block
    assert "RELEVANT CASE EVIDENCE" in block


def test_assembled_diagnose_prompt_includes_case_grounding() -> None:
    prompt = assemble_execution_prompt(_base_ctx(mode="DIAGNOSE", allow_case=True))
    assert "RELEVANT CASE EVIDENCE" in prompt
    assert "do not quote verbatim" in prompt


def test_assembled_discovery_prompt_omits_case_grounding_when_early() -> None:
    prompt = assemble_execution_prompt(_base_ctx(mode="DISCOVERY", allow_case=False))
    assert "RELEVANT CASE EVIDENCE" not in prompt


def test_assembled_sales_prompt_includes_case_grounding_when_allowed() -> None:
    prompt = assemble_execution_prompt(_base_ctx(mode="SALES", allow_case=True))
    assert "RELEVANT CASE EVIDENCE" in prompt
