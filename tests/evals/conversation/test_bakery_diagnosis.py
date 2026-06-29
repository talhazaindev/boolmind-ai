"""Bakery diagnosis scenario eval."""

import json
from pathlib import Path

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.orchestrator.strategy_diagnosis import infer_growth_blocker
from app.advisor.types import ReadinessFlags, SessionMetadata

_DIR = Path(__file__).parent


def test_bakery_underperforming_channels_mode() -> None:
    scenario = json.loads((_DIR / "bakery_diagnosis.json").read_text(encoding="utf-8"))
    turn = scenario["turns"][0]
    history = [
        "I own a small local business, growth slowed",
        "We run a local bakery, customers from referrals nearby",
        "We have Google Business Profile and Instagram",
    ]
    meta = SessionMetadata(
        business_type="bakery",
        pain_point="growth slowed",
        goals="online presence",
        channels_active=["google_business", "instagram"],
        message_count=4,
    )
    mode = select_conversation_mode(
        turn["user"], meta, ReadinessFlags(), history_texts=history
    )
    assert mode == turn["expect_mode"]
    assert infer_growth_blocker(meta, turn["user"], history) == turn["expect_blocker"]

    block = build_recommendation_block(meta, mode, user_message=turn["user"], history=history)
    assert "STRATEGIC DIAGNOSIS" in block
    assert "referral" in block.lower() or "satisfaction" in block.lower()
