"""Consulting reasoning engine tests — hypotheses, phases, convergence."""

from app.advisor.orchestrator.conversation_evaluator import _apply_reasoning_context
from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.industry_strategy import should_defer_boolmind_pitch
from app.advisor.orchestrator.reasoning_engine import (
    build_convergence_block,
    build_hypothesis_block,
    build_insight_block,
    build_reasoning_prompt_blocks,
    build_solution_exploration_block,
    detect_business_model,
    generate_hypotheses,
    rank_hypotheses,
    select_differentiating_question,
    select_reasoning_phase,
    update_reasoning_state,
)
from app.advisor.orchestrator.response_guards import (
    response_contains_premature_boolmind,
    response_missing_hypothesis_structure,
)
from app.advisor.orchestrator.strategy_diagnosis import (
    detect_growth_hypotheses,
    growth_diagnostic_question,
)
from app.advisor.types import (
    EvidenceEntry,
    HypothesisState,
    ReadinessFlags,
    SessionMetadata,
    TurnEvaluation,
)


_TRIAL_CONVERSION = "Our trial conversion dropped significantly last quarter."
_CANCEL_WEEK2 = "Customers cancel after week 2 of their subscription."
_TEACHER_MSG = (
    "Enrollment is increasing but teachers feel overwhelmed during peak periods."
)


def test_trial_conversion_generates_saas_hypotheses() -> None:
    meta = SessionMetadata(business_type="B2B SaaS", pain_point="trial conversion")
    pairs = detect_growth_hypotheses(meta, _TRIAL_CONVERSION, [])
    assert len(pairs) >= 3
    ids = {p[0] for p in pairs}
    assert "pricing_sensitivity" in ids or "onboarding_friction" in ids


def test_trial_conversion_differentiating_question() -> None:
    meta = SessionMetadata(
        business_type="B2B SaaS",
        business_model="saas",
        pain_point="trial conversion",
    )
    q = growth_diagnostic_question(meta, _TRIAL_CONVERSION, [])
    assert "onboarding" in q.lower() or "pricing" in q.lower() or "disengage" in q.lower()


def test_cancel_week2_hypothesis_test_question() -> None:
    meta = SessionMetadata(
        business_type="subscription business",
        business_model="subscription",
        pain_point="churn after week 2",
        message_count=3,
        reasoning_phase="hypothesis_testing",
    )
    meta = update_reasoning_state(meta, _CANCEL_WEEK2, [])
    block = build_reasoning_prompt_blocks(meta, _CANCEL_WEEK2, [])
    assert "HYPOTHESIS TEST" in block or "HYPOTHESIS GENERATION" in block
    q = select_differentiating_question(meta.hypotheses, "subscription")
    assert "changed" in q.lower() or "recently" in q.lower()


def test_teacher_enrollment_insight_block() -> None:
    meta = SessionMetadata(
        business_type="language-learning center",
        business_model="education",
        pain_point="teacher turnover",
        reasoning_phase="strategic_insight",
    )
    meta.hypotheses = rank_hypotheses(
        [("workload", "workload — overwhelm during peak demand")],
        _TEACHER_MSG,
        [],
    )
    block = build_insight_block(meta, meta.hypotheses)
    assert "operational support" in block.lower() or "growth" in block.lower()
    assert "Do NOT recommend" in block or "No solution" in block


def test_convergence_block_more_less_likely() -> None:
    meta = SessionMetadata(message_count=6, last_convergence_turn=3)
    meta.evidence_log = [
        EvidenceEntry(
            turn=5,
            text="onboarding completion correlates with conversion",
            supports=["onboarding_friction"],
        )
    ]
    hypotheses = [
        HypothesisState(id="onboarding_friction", label="onboarding friction", confidence=0.55, status="active"),
        HypothesisState(id="pricing_sensitivity", label="pricing sensitivity", confidence=0.25, status="active"),
        HypothesisState(id="competition", label="competition", confidence=0.15, status="active"),
        HypothesisState(id="wrong_segment", label="wrong segment", confidence=0.05, status="active"),
    ]
    block = build_convergence_block(meta, hypotheses)
    assert "More likely" in block
    assert "Less likely" in block


def test_solution_exploration_no_boolmind() -> None:
    meta = SessionMetadata(reasoning_phase="solution_exploration")
    meta.hypotheses = [
        HypothesisState(id="onboarding_friction", label="onboarding friction", confidence=0.7, status="active"),
    ]
    block = build_solution_exploration_block(meta, meta.hypotheses)
    assert "Do NOT mention Boolmind" in block
    assert "onboarding" in block.lower()


def test_boolmind_deferred_until_phase_7() -> None:
    meta = SessionMetadata(message_count=10, stage_reached="INTEREST")
    assert should_defer_boolmind_pitch(meta) is True
    meta.reasoning_phase = "boolmind_positioning"
    assert should_defer_boolmind_pitch(meta) is False


def test_boolmind_allowed_in_positioning_phase() -> None:
    assert response_contains_premature_boolmind(
        "Boolmind could help with onboarding", "boolmind_positioning"
    ) is False
    assert response_contains_premature_boolmind(
        "Boolmind could help", "hypothesis_testing"
    ) is True


def test_phase_gates_recommend_mode() -> None:
    meta = SessionMetadata(
        business_type="SaaS",
        pain_point="conversion",
        goals="grow revenue",
        message_count=5,
        reasoning_phase="hypothesis_testing",
    )
    mode = select_conversation_mode("still testing", meta, ReadinessFlags())
    assert mode == "diagnose"

    meta.reasoning_phase = "solution_exploration"
    mode = select_conversation_mode("what options do we have", meta, ReadinessFlags())
    assert mode == "recommend"


def test_hypothesis_generation_block_lists_ranked() -> None:
    hypotheses = rank_hypotheses(
        [
            ("pricing_sensitivity", "pricing sensitivity"),
            ("onboarding_friction", "onboarding friction"),
            ("competition", "competition"),
        ],
        _TRIAL_CONVERSION,
        [],
    )
    block = build_hypothesis_block(hypotheses, "Where do users disengage?")
    assert "HYPOTHESIS GENERATION" in block
    assert "pricing" in block.lower() or "onboarding" in block.lower()


def test_missing_hypothesis_structure_guard() -> None:
    assert response_missing_hypothesis_structure(
        "Tell me more about your business.", "hypothesis_generation"
    ) is True
    assert response_missing_hypothesis_structure(
        "Several possibilities: pricing, onboarding, and competition.",
        "hypothesis_generation",
    ) is False


def test_business_model_inference_from_evaluator() -> None:
    evaluation = TurnEvaluation(
        profile_updates={"business_type": "B2B SaaS startup"},
    )
    result = _apply_reasoning_context(evaluation, SessionMetadata())
    assert result.profile_updates.get("business_model") == "saas"


def test_detect_business_model_saas() -> None:
    meta = SessionMetadata(business_type="software company")
    assert detect_business_model(meta, "trial conversion dropped", []) == "saas"


def test_reasoning_state_advances_phase() -> None:
    meta = SessionMetadata(
        business_type="SaaS",
        pain_point="trial conversion",
        message_count=2,
    )
    updated = update_reasoning_state(meta, _TRIAL_CONVERSION, [])
    assert updated.reasoning_phase in (
        "hypothesis_generation",
        "hypothesis_testing",
    )
    assert len(updated.hypotheses) >= 3


def test_select_reasoning_phase_discovery_to_generation() -> None:
    meta = SessionMetadata(business_type="retail")
    assert select_reasoning_phase(meta) == "hypothesis_generation"
