"""Workforce retention diagnosis and validation gate tests."""

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.diagnostic_validation import (
    hypotheses_need_validation,
    response_contains_premature_solutions,
    user_provided_evidence_without_confirmation,
)
from app.advisor.orchestrator.goal_context import detect_primary_goal
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.orchestrator.workforce_diagnosis import (
    build_workforce_diagnosis_block,
    detect_workforce_hypotheses,
    should_diagnose_workforce,
)
from app.advisor.types import ReadinessFlags, SessionMetadata

_LANG_T1 = (
    "I run a small language-learning center. Over the last two years, student enrollment "
    "has been steadily increasing, but teacher turnover has become a major problem. We "
    "spend a lot of time recruiting and training instructors, and some students complain "
    "when their teacher changes. I'm not sure whether the issue is compensation, "
    "workload, management, or something else."
)

_LANG_T2 = (
    "The most common feedback is that teachers feel overwhelmed during peak enrollment "
    "periods, and some say there isn't much opportunity for career growth. Compensation "
    "complaints come up occasionally, but not as often."
)


def test_language_center_is_workforce_not_throughput() -> None:
    meta = SessionMetadata()
    assert detect_problem_dimension(meta, _LANG_T1, []) == "workforce"
    assert detect_primary_goal(meta, _LANG_T1, []) == "workforce"


def test_turn1_diagnose_comparative_not_open_ended() -> None:
    meta = SessionMetadata(
        business_type="language-learning center",
        primary_goal="workforce",
        problem_dimension="workforce",
        message_count=1,
    )
    mode = select_conversation_mode(_LANG_T1, meta, ReadinessFlags(), history_texts=[])
    assert mode == "diagnose"
    block = build_recommendation_block(meta, mode, user_message=_LANG_T1, history=[])
    assert "WORKFORCE DIAGNOSIS" in block
    assert "compensation" in block.lower() or "workload" in block.lower()


def test_turn2_evidence_still_requires_validation() -> None:
    meta = SessionMetadata(
        business_type="language-learning center",
        primary_goal="workforce",
        problem_dimension="workforce",
        message_count=2,
    )
    history = [_LANG_T1]
    hypotheses = detect_workforce_hypotheses(meta, _LANG_T2, history)
    assert "workload" in hypotheses
    assert "career_growth" in hypotheses
    assert user_provided_evidence_without_confirmation(_LANG_T2, history) is True
    assert should_diagnose_workforce(meta, _LANG_T2, history) is True
    assert hypotheses_need_validation(hypotheses, _LANG_T2, history, None) is True

    mode = select_conversation_mode(_LANG_T2, meta, ReadinessFlags(), history_texts=history)
    assert mode == "diagnose"
    block = build_workforce_diagnosis_block(meta, _LANG_T2, history)
    assert "TRADEOFF" in block
    assert "have you considered" in block.lower() or "Do NOT" in block
    assert "professional development" in block.lower() or "intervention" in block.lower()


def test_premature_solution_detection() -> None:
    bad = (
        "Have you considered implementing staffing adjustments, "
        "professional development programs, or mentorship opportunities?"
    )
    assert response_contains_premature_solutions(bad) is True
