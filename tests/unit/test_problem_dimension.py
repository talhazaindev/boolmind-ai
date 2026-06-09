"""Problem dimension detection — metric before framework."""

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.goal_context import detect_primary_goal
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.types import ReadinessFlags, SessionMetadata

_EVENT_PLANNING = (
    "I run a small event planning company. Business is doing well, but my team is "
    "constantly overwhelmed. We seem busy all the time, yet our profits haven't "
    "increased much over the last year. I'm trying to figure out whether the problem "
    "is pricing, efficiency, or something else."
)

_FURNITURE_THROUGHPUT = (
    "Demand has been increasing, but we're struggling to keep up with orders. "
    "Projects are getting delayed, customers are frustrated."
)


def test_event_planning_is_profitability_not_throughput() -> None:
    meta = SessionMetadata()
    assert detect_problem_dimension(meta, _EVENT_PLANNING, []) == "profitability"
    assert detect_primary_goal(meta, _EVENT_PLANNING, []) == "profitability"


def test_furniture_delays_stay_throughput() -> None:
    meta = SessionMetadata(business_type="custom furniture manufacturing")
    assert detect_problem_dimension(meta, _FURNITURE_THROUGHPUT, []) == "throughput"
    assert detect_primary_goal(meta, _FURNITURE_THROUGHPUT, []) == "operations"


def test_event_planning_diagnosis_uses_pricing_not_materials() -> None:
    meta = SessionMetadata(
        business_type="event planning company",
        primary_goal="profitability",
        problem_dimension="profitability",
        message_count=1,
    )
    mode = select_conversation_mode(
        _EVENT_PLANNING, meta, ReadinessFlags(), history_texts=[]
    )
    assert mode == "diagnose"
    block = build_recommendation_block(meta, mode, user_message=_EVENT_PLANNING, history=[])
    assert "PROFITABILITY DIAGNOSIS" in block
    assert "pricing" in block.lower()
    assert "efficiency" in block.lower()
    q_line = block.split('"')[-2] if '"' in block else block
    assert "materials" not in q_line.lower()
    assert "production capacity" not in q_line.lower()
