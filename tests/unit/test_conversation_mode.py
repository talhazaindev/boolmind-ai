"""Conversation mode selection tests."""

from app.advisor.orchestrator.conversation_mode import (
    select_conversation_mode,
    update_consecutive_question_turns,
)
from app.advisor.types import ReadinessFlags, SessionMetadata


def test_select_discover_by_default() -> None:
    mode = select_conversation_mode(
        "Hello",
        SessionMetadata(),
        ReadinessFlags(),
    )
    assert mode == "discover"


def test_select_advise_on_advice_request() -> None:
    mode = select_conversation_mode(
        "What would you recommend in my situation?",
        SessionMetadata(),
        ReadinessFlags(),
    )
    assert mode == "advise"


def test_select_advise_on_roi() -> None:
    mode = select_conversation_mode(
        "Is a $5000 investment worth it?",
        SessionMetadata(),
        ReadinessFlags(),
    )
    assert mode == "advise"


def test_select_recommend_after_minimum_context() -> None:
    meta = SessionMetadata(
        message_count=4,
        industry="education",
        pain_point="manual enrollment",
        goals="online presence",
    )
    mode = select_conversation_mode(
        "Tell me more",
        meta,
        ReadinessFlags(),
    )
    assert mode == "recommend"


def test_force_advise_after_two_consecutive_questions() -> None:
    meta = SessionMetadata(consecutive_question_turns=2)
    mode = select_conversation_mode(
        "Okay",
        meta,
        ReadinessFlags(),
    )
    assert mode == "advise"


def test_consecutive_question_counter_resets_on_advise() -> None:
    meta = SessionMetadata(consecutive_question_turns=2)
    count = update_consecutive_question_turns(meta, "Here is my recommendation.", "advise")
    assert count == 0


def test_consecutive_question_counter_increments() -> None:
    meta = SessionMetadata(consecutive_question_turns=1)
    count = update_consecutive_question_turns(meta, "What industry are you in?", "discover")
    assert count == 2
