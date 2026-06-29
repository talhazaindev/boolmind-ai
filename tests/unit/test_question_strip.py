"""Tests for redundant question stripping."""

from app.advisor.orchestrator.question_append import strip_redundant_questions
from app.advisor.orchestrator.signals.v1 import UNKNOWN_TO_QUESTION
from app.advisor.types import HypothesisSnapshot, SessionMetadata


def test_strip_scale_question_when_known() -> None:
    snap = HypothesisSnapshot(
        scale_indicators=["220 applications/day"],
        resolved_unknowns=["scale"],
    )
    meta = SessionMetadata(data_context="220 applications/day")
    body = (
        "That is a significant backlog. "
        f"{UNKNOWN_TO_QUESTION['scale']}"
    )
    cleaned = strip_redundant_questions(body, snap, meta)
    assert "volume" not in cleaned.lower()
    assert "backlog" in cleaned.lower()
