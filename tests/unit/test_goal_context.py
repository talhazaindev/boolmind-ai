"""Goal context and domain drift prevention tests."""

from app.advisor.orchestrator.conversation_evaluator import _apply_goal_context
from app.advisor.orchestrator.goal_context import (
    detect_primary_goal,
    filter_missing_for_goal,
    goal_lock_prompt_block,
    growth_discovery_question,
)
from app.advisor.types import ReadinessFlags, SessionMetadata, TurnEvaluation


def test_detect_growth_goal_from_conversation() -> None:
    history = [
        "I want to grow but have limited budget",
        "new customers aren't discovering us, growth stalled",
    ]
    meta = SessionMetadata(pain_point="discovery", goals="growth")
    assert detect_primary_goal(meta, "accounting services", history) == "growth_marketing"


def test_filter_removes_data_context_for_growth() -> None:
    missing = ["business_context", "data_context", "product_fit"]
    filtered = filter_missing_for_goal(missing, "growth_marketing")
    assert "data_context" not in filtered
    assert "product_fit" not in filtered


def test_accounting_growth_question_not_document_ops() -> None:
    meta = SessionMetadata(
        business_type="accounting and bookkeeping",
        industry="professional services",
        primary_goal="growth_marketing",
        pain_point="new customer discovery",
        goals="growth",
    )
    q = growth_discovery_question(meta)
    q_lower = q.lower()
    assert any(kw in q_lower for kw in ("channel", "referral", "find", "discover", "customer"))
    assert "document" not in q_lower


def test_goal_lock_blocks_ops_drift() -> None:
    meta = SessionMetadata(business_type="accounting firm")
    block = goal_lock_prompt_block("growth_marketing", meta)
    assert "document management" in block.lower()
    assert "NOT internal operations" in block


def test_apply_goal_context_rewrites_drift_question() -> None:
    meta = SessionMetadata(
        business_type="accounting",
        goals="growth",
        pain_point="discovery stalled",
        primary_goal="growth_marketing",
    )
    ev = TurnEvaluation(
        missing_fields=["data_context", "product_fit"],
        next_discovery_question="How do you handle document management?",
        readiness=ReadinessFlags(),
    )
    history = ["growth stalled", "need more customers"]
    result = _apply_goal_context(
        ev, meta, message="accounting and bookkeeping services", history_texts=history
    )
    assert "data_context" not in result.missing_fields
    assert "document" not in result.next_discovery_question.lower()
