"""Conversation scenario evals — deterministic mode/intent checks (no live Groq)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.advisor.orchestrator.conversation_evaluator import _detect_user_sophistication
from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.intent_classifier import classify_intent
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.types import ReadinessFlags, SessionMetadata

_SCENARIOS_DIR = Path(__file__).parent


def _load_scenario(name: str) -> dict:
    path = _SCENARIOS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _meta_after_turns(turn_index: int) -> SessionMetadata:
    """Simulate profile accumulation for music academy scenario."""
    meta = SessionMetadata(message_count=turn_index + 1)
    if turn_index >= 0:
        meta.industry = "education"
        meta.business_type = "music academy"
    if turn_index >= 1:
        meta.goals = "online presence and enrollment"
        meta.pain_point = "word of mouth only, manual operations"
    if turn_index >= 2:
        meta.constraints = "limited budget"
    return meta


@pytest.mark.parametrize("turn_index", range(7))
def test_music_academy_mode_selection(turn_index: int) -> None:
    scenario = _load_scenario("music_academy")
    turn = scenario["turns"][turn_index]
    meta = _meta_after_turns(turn_index)
    mode = select_conversation_mode(turn["user"], meta, ReadinessFlags())
    assert mode == turn["expect_mode"], (
        f"Turn {turn_index}: expected {turn['expect_mode']}, got {mode}"
    )


def test_music_academy_intent_on_objection_turn() -> None:
    scenario = _load_scenario("music_academy")
    turn = scenario["turns"][5]
    intent = classify_intent(turn["user"])
    assert intent.intent == turn["expect_intent"]


def test_music_academy_intent_on_roi_turn() -> None:
    scenario = _load_scenario("music_academy")
    turn = scenario["turns"][6]
    intent = classify_intent(turn["user"])
    assert intent.intent == turn["expect_intent"]


def test_low_sophistication_detection() -> None:
    scenario = _load_scenario("music_academy")
    turn = scenario["turns"][3]
    assert _detect_user_sophistication(turn["user"]) == "low"


def test_recommendation_block_is_industry_specific() -> None:
    meta = _meta_after_turns(4)
    block = build_recommendation_block(
        meta, "recommend", include_boolmind=True,
    )
    assert "rag_query" in block
    assert "Diagnose" in block or "diagnose" in block.lower()


def test_pass_criteria_documented() -> None:
    scenario = _load_scenario("music_academy")
    criteria = scenario["pass_criteria"]
    assert criteria["max_consecutive_question_turns"] == 2
    assert criteria["no_diy_as_primary_in_advise_recommend"] is True
