"""Strategic diagnosis layer tests — generic signals."""

from app.advisor.orchestrator.conversation_mode import select_conversation_mode
from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.orchestrator.strategy_diagnosis import (
    build_diagnosis_block,
    channels_underperforming,
    detect_active_channels,
    diagnostic_question,
    infer_growth_blocker,
    should_insight_before_tactics,
    strategic_insight,
)
from app.advisor.types import ReadinessFlags, SessionMetadata


def test_detect_channels_generic() -> None:
    meta = SessionMetadata()
    channels = detect_active_channels(
        meta,
        "We already have a Google Business Profile and an Instagram page",
    )
    assert "google_business" in channels
    assert "instagram" in channels


def test_underperforming_channels_trigger_diagnose_mode() -> None:
    meta = SessionMetadata(
        business_type="any local business",
        pain_point="growth slowed",
        goals="more customers",
        channels_active=["google_business", "instagram"],
        message_count=3,
    )
    history = ["referrals work well"]
    msg = "We already have Google and Instagram but neither brings new customers"
    assert channels_underperforming(msg, history) is True
    assert select_conversation_mode(
        msg, meta, ReadinessFlags(), history_texts=history
    ) == "diagnose"


def test_referral_insight_generic_not_industry_specific() -> None:
    meta = SessionMetadata(business_type="any business", pain_point="slow growth")
    history = ["customers come from referrals"]
    msg = "online channels don't bring new customers"
    insight = strategic_insight(meta, msg, history)
    assert "satisfied" in insight.lower() or "referral" in insight.lower()
    assert "bakery" not in insight.lower()
    assert "fitness" not in insight.lower()


def test_diagnosis_block_uses_business_label() -> None:
    meta = SessionMetadata(business_type="custom craft workshop")
    block = build_diagnosis_block(
        meta,
        "growth stalled",
        ["referrals work"],
    )
    assert "STRATEGIC DIAGNOSIS" in block
    assert "rag_query" in block
    assert "custom craft workshop" in diagnostic_question(meta)


def test_insight_before_tactics_any_business_with_referrals() -> None:
    meta = SessionMetadata(business_type="local fitness studio", goals="grow")
    history = ["looking for ways to grow"]
    msg = "Most members come from referrals"
    assert should_insight_before_tactics(meta, msg, history) is True


def test_recommendation_block_diagnosis_not_generic_seo_list() -> None:
    meta = SessionMetadata(
        business_type="any business",
        pain_point="discovery",
        goals="growth",
        channels_active=["google_business"],
    )
    history = ["referrals work"]
    msg = "neither Google nor Instagram brings new customers"
    block = build_recommendation_block(meta, "advise", user_message=msg, history=history)
    assert "STRATEGIC DIAGNOSIS" in block
    assert "rag_query" in block


def test_growth_blocker_discovery() -> None:
    meta = SessionMetadata()
    assert infer_growth_blocker(meta, "new customers aren't discovering us", []) == "discovery"
