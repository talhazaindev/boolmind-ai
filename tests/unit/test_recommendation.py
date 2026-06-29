"""Recommendation block builder tests."""

from app.advisor.orchestrator.recommendation import build_recommendation_block
from app.advisor.types import SessionMetadata


def test_recommendation_block_includes_known_context() -> None:
    meta = SessionMetadata(
        industry="education",
        business_type="music academy",
        pain_point="manual enrollment",
        goals="online presence",
        constraints="limited budget",
        message_count=6,
        stage_reached="QUALIFY",
    )
    block = build_recommendation_block(meta, "recommend", include_boolmind=True)
    assert "RECOMMENDATION REQUIRED" in block
    assert "rag_query" in block


def test_advisory_block_for_advise_mode() -> None:
    meta = SessionMetadata(goals="grow online", message_count=6, stage_reached="QUALIFY")
    block = build_recommendation_block(meta, "advise", include_boolmind=True)
    assert "ADVISORY DELIVERY REQUIRED" in block
    assert "Phase 3" in block or "Boolmind" in block
