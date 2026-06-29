"""Unit tests for conversation_planner — multi-turn diagnostic sequencing."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.advisor.knowledge.ontology_loader import _load_archetypes
from app.advisor.orchestrator.prompt_composition import build_execution_mode_block
from app.advisor.pipeline.conversation_planner import ConversationPlanner, TurnPlan
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import HypothesisSnapshot, SessionMetadata


def _archetype_by_id(archetype_id: str):
    for arch in _load_archetypes():
        if arch.id == archetype_id:
            return arch
    raise KeyError(archetype_id)


@pytest.fixture
def planner() -> ConversationPlanner:
    return ConversationPlanner()


def test_identify_vertical_when_no_vertical(planner: ConversationPlanner) -> None:
    plan = planner.plan(
        session_metadata=SessionMetadata(),
        depth=DiagnosticDepth(score=0),
        matched_archetypes=[],
        message_count=0,
    )
    assert plan.this_turn_priority == "identify_vertical"


def test_turns_one_and_two_never_allow_solution_hint(planner: ConversationPlanner) -> None:
    depth = DiagnosticDepth(score=80)
    for message_count in (0, 1):
        plan = planner.plan(
            session_metadata=SessionMetadata(
                industry="logistics",
                data_context="50 employees",
                pain_point="driver wait times",
            ),
            depth=depth,
            matched_archetypes=[],
            message_count=message_count,
        )
        assert plan.allow_solution_hint is False


def test_force_discovery_for_message_count_up_to_three(planner: ConversationPlanner) -> None:
    depth = DiagnosticDepth(score=80)
    for message_count in (0, 1, 2, 3):
        plan = planner.plan(
            session_metadata=SessionMetadata(industry="retail"),
            depth=depth,
            matched_archetypes=[],
            message_count=message_count,
        )
        assert plan.force_discovery_mode is True


def test_force_discovery_false_when_mid_and_depth_allows(planner: ConversationPlanner) -> None:
    plan = planner.plan(
        session_metadata=SessionMetadata(
            industry="retail",
            data_context="20 staff",
            pain_point="slow approvals",
        ),
        depth=DiagnosticDepth(score=65),
        matched_archetypes=[],
        message_count=4,
    )
    assert plan.force_discovery_mode is False


def test_allow_case_reference_gated_in_early_turns(planner: ConversationPlanner) -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    early = planner.plan(
        session_metadata=SessionMetadata(industry="services"),
        depth=DiagnosticDepth(score=40),
        matched_archetypes=[lead_leakage],
        message_count=2,
    )
    assert early.allow_case_reference is False

    mid = planner.plan(
        session_metadata=SessionMetadata(industry="services"),
        depth=DiagnosticDepth(score=40),
        matched_archetypes=[lead_leakage],
        message_count=5,
    )
    assert mid.allow_case_reference is True


def test_project_next_gaps(planner: ConversationPlanner) -> None:
    hints = planner._project_next_gaps(
        SessionMetadata(),
        DiagnosticDepth(score=0),
        "identify_vertical",
    )
    assert hints == ["identify_scale", "identify_primary_symptom"]


def test_plan_never_raises(planner: ConversationPlanner) -> None:
    bad_meta = MagicMock()
    bad_meta.active_business_vertical = None
    bad_meta.industry = None
    bad_meta.data_context = None
    bad_meta.business_memory_lines = []
    bad_meta.pain_point = None
    bad_meta.issue_tree = {}
    type(bad_meta).pain_point = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

    plan = planner.plan(
        session_metadata=bad_meta,
        depth=DiagnosticDepth(score=999),
        matched_archetypes=[],
        message_count=-1,
    )
    assert isinstance(plan, TurnPlan)
    assert plan.this_turn_priority == "identify_vertical"


def test_planner_guidance_in_prompt_when_force_discovery() -> None:
    plan = TurnPlan(
        this_turn_priority="identify_vertical",
        force_discovery_mode=True,
    )
    block = build_execution_mode_block(
        "DISCOVERY",
        HypothesisSnapshot(),
        turn_plan=plan,
    )
    assert "PLANNER GUIDANCE" in block
    assert "DIAGNOSTIC MODE" in block


def test_case_hook_in_prompt_only_when_allowed() -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    early_plan = TurnPlan(
        this_turn_priority="confirm_root_cause",
        allow_case_reference=False,
    )
    early_block = build_execution_mode_block(
        "DIAGNOSE",
        HypothesisSnapshot(),
        turn_plan=early_plan,
        matched_archetypes=[lead_leakage],
    )
    assert "PLANNER GUIDANCE" not in early_block
    if lead_leakage.case_hook:
        assert lead_leakage.case_hook not in early_block

    late_plan = TurnPlan(
        this_turn_priority="confirm_root_cause",
        allow_case_reference=True,
    )
    late_block = build_execution_mode_block(
        "DIAGNOSE",
        HypothesisSnapshot(),
        turn_plan=late_plan,
        matched_archetypes=[lead_leakage],
    )
    if lead_leakage.case_hook:
        assert lead_leakage.case_hook in late_block


def test_turn_pipeline_returns_turn_plan() -> None:
    result = TurnPipeline.run(
        SessionMetadata(message_count=0),
        "We run a logistics company and drivers wait too long at pickup.",
        [],
    )
    assert result.turn_plan is not None
    assert result.turn_plan.this_turn_priority in {
        "identify_vertical",
        "identify_scale",
        "identify_primary_symptom",
        "confirm_root_cause",
        "quantify_impact",
        "discover_constraint",
        "solution_readiness",
    }
