"""Business memory tests."""

from app.advisor.orchestrator.business_memory import (
    MEMORY_EXPIRE_CONFIDENCE,
    update_business_memory,
)
from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.product_fit_mapper import map_product_fit
from app.advisor.types import ScoredMemoryLine, SessionMetadata


def test_memory_expire_after_low_confidence() -> None:
    meta = SessionMetadata(message_count=10)
    snapshot = update_hypothesis_snapshot(meta, "hello", [])
    fit = map_product_fit(meta, "hello", [])
    stale = ScoredMemoryLine(
        key="industry",
        value="retail",
        confidence=0.4,
        source_turn=1,
        last_confirmed_turn=1,
    )
    lines, mem = update_business_memory(
        [stale], meta, snapshot, fit, "hello", turn=10
    )
    assert all(line.key != "industry" for line in lines)
    assert all(line.confidence >= MEMORY_EXPIRE_CONFIDENCE for line in mem.lines)


def test_memory_reconfirm_boosts_confidence() -> None:
    meta = SessionMetadata(industry="logistics", message_count=2)
    snapshot = update_hypothesis_snapshot(
        meta, "logistics delays in dispatch", []
    )
    fit = map_product_fit(meta, "logistics delays", [])
    existing = ScoredMemoryLine(
        key="industry",
        value="logistics",
        confidence=0.85,
        source_turn=1,
        last_confirmed_turn=1,
    )
    lines, _ = update_business_memory(
        [existing], meta, snapshot, fit, "logistics delays", turn=2
    )
    industry = next(l for l in lines if l.key == "industry")
    assert industry.confidence >= 0.85
    assert industry.last_confirmed_turn == 2
