"""Prompt composition tests."""

from app.advisor.orchestrator.prompt_composition import (
    MODE_PROMPT_COMPOSITION,
    assemble_execution_prompt,
    build_execution_mode_block,
)
from app.advisor.types import (
    BusinessMemorySnapshot,
    HypothesisSnapshot,
    ProductFitDecision,
    RouterOutput,
    SessionMetadata,
    TurnContext,
)


def test_frozen_composition_per_mode() -> None:
    assert "grounding" in MODE_PROMPT_COMPOSITION["RAG_ONLY"]
    assert "hypothesis" not in MODE_PROMPT_COMPOSITION["RAG_ONLY"]
    assert "deliverable" in MODE_PROMPT_COMPOSITION["ARCHITECTURE"]


def test_diagnose_depth_format() -> None:
    early = build_execution_mode_block(
        "DIAGNOSE", HypothesisSnapshot(diagnose_depth="early")
    )
    late = build_execution_mode_block(
        "DIAGNOSE", HypothesisSnapshot(diagnose_depth="late")
    )
    assert "empathetic" in early.lower() or "natural" in early.lower()
    assert "Tradeoff" in late or "inference" in late.lower()
    assert "Observation:" not in early


def test_assemble_includes_executor_rule() -> None:
    ctx = TurnContext(
        session_id="s1",
        message="hi",
        history_texts=(),
        frozen_meta=SessionMetadata(),
        extracted_meta=SessionMetadata(),
        snapshot=HypothesisSnapshot(),
        business_memory=BusinessMemorySnapshot(),
        product_fit_decision=ProductFitDecision(),
        router_output=RouterOutput(intent="general", mode="DISCOVERY"),
    )
    prompt = assemble_execution_prompt(ctx)
    assert "EXECUTOR RULE" in prompt
    assert "DISCOVERY" in prompt
