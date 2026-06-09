"""Operations/scaling scenarios — any business with delivery bottlenecks."""

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.goal_context import detect_primary_goal
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.types import ReadinessFlags, SessionMetadata

_SCENARIOS = (
    (
        "custom furniture manufacturing",
        "Demand is increasing but we cannot keep up with orders. Projects are delayed.",
    ),
    (
        "catering business",
        "More bookings than we can handle. Delays happen waiting for supplies and client menu approvals.",
    ),
    (
        "print shop",
        "Orders are backing up. Not sure if we need more staff, better scheduling, or faster suppliers.",
    ),
)


def test_scaling_problems_trigger_operations_diagnose() -> None:
    for business_type, pain in _SCENARIOS:
        meta = SessionMetadata(business_type=business_type, message_count=2)
        history = [pain]
        msg = (
            "Some jobs move fast, others get stuck. I'm not sure whether it's "
            "materials, approvals, or capacity."
        )
        assert detect_primary_goal(meta, msg, history) == "operations", business_type
        mode = select_conversation_mode(
            msg, meta, ReadinessFlags(), history_texts=history
        )
        assert mode == "diagnose", business_type
        block = build_recommendation_block(meta, mode, user_message=msg, history=history)
        assert "OPERATIONS DIAGNOSIS" in block
        assert "TRADEOFF" in block
