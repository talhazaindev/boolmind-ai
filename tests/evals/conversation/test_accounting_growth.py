"""Accounting firm growth scenario — no ops drift."""

import json
from pathlib import Path

from app.advisor.orchestrator.conversation_evaluator import _apply_goal_context
from app.advisor.orchestrator.goal_context import detect_primary_goal, growth_discovery_question
from app.advisor.orchestrator.industry_strategy import business_label
from app.advisor.types import ReadinessFlags, SessionMetadata, TurnEvaluation

_DIR = Path(__file__).parent


def test_accounting_firm_stays_on_growth_thread() -> None:
    scenario = json.loads((_DIR / "accounting_growth.json").read_text(encoding="utf-8"))
    turn = scenario["turns"][0]
    history = [
        "I run a small local business trying to grow with limited budget",
        "Most customers come through referrals but new customers aren't discovering us",
    ]
    meta = SessionMetadata(
        business_type="accounting firm",
        pain_point="new customer discovery stalled",
        goals="growth",
        primary_goal="growth_marketing",
    )
    assert detect_primary_goal(meta, turn["user"], history) == "growth_marketing"
    assert "accounting" in business_label(meta).lower()

    ev = _apply_goal_context(
        TurnEvaluation(
            missing_fields=["data_context"],
            next_discovery_question="How do you manage sensitive financial documents?",
            readiness=ReadinessFlags(),
        ),
        meta,
        message=turn["user"],
        history_texts=history,
    )
    assert "document" not in ev.next_discovery_question.lower()
    assert "data_context" not in ev.missing_fields

    q = growth_discovery_question(meta, turn["user"])
    combined = (q + ev.next_discovery_question).lower()
    assert any(kw in combined for kw in ("channel", "referral", "find", "discover", "customer"))
    assert "document" not in combined
