"""Generic growth consulting scenarios — any business type."""

import json
from pathlib import Path

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.intent_classifier import is_channel_prioritization
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.orchestrator.strategy_diagnosis import (
    build_opening_value_block,
    should_insight_before_tactics,
)
from app.advisor.types import ReadinessFlags, SessionMetadata

_DIR = Path(__file__).parent


def test_opening_channel_confusion_any_business() -> None:
    opening = (
        "I'm not sure where to invest — websites, SEO, social media, ads, or AI — "
        "what's actually worth focusing on?"
    )
    assert is_channel_prioritization(opening) is True
    assert "business model" in build_opening_value_block().lower()


def test_local_business_referrals_triggers_diagnosis_not_vertical_playbook() -> None:
    """Any local business + referrals + growth → diagnose, not hardcoded vertical advice."""
    for business_type in (
        "local fitness studio",
        "bakery",
        "accounting firm",
        "pet grooming salon",
    ):
        history = ["I want to grow my business"]
        meta = SessionMetadata(business_type=business_type, goals="grow", message_count=2)
        msg = f"We run a {business_type}. Most customers come from referrals."
        assert should_insight_before_tactics(meta, msg, history) is True
        mode = select_conversation_mode(
            msg, meta, ReadinessFlags(), history_texts=history
        )
        assert mode == "diagnose", business_type
        block = build_recommendation_block(meta, mode, user_message=msg, history=history)
        assert "STRATEGIC DIAGNOSIS" in block
        assert "rag_query" in block
        assert business_type in block or business_type.split()[0] in block.lower()


def test_underperforming_channels_any_business() -> None:
    scenario = json.loads((_DIR / "bakery_diagnosis.json").read_text(encoding="utf-8"))
    turn = scenario["turns"][0]
    meta = SessionMetadata(
        business_type="any local business",
        channels_active=["google_business", "instagram"],
        message_count=4,
    )
    history = ["local business", "referrals"]
    mode = select_conversation_mode(
        turn["user"], meta, ReadinessFlags(), history_texts=history
    )
    assert mode == "diagnose"
