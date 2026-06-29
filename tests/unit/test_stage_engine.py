"""Stage engine tests."""

from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.pipeline.stage_engine import promote_funnel_stage
from app.advisor.types import SessionMetadata


def test_funnel_promotes_to_interest_on_discovery_exit() -> None:
    meta = SessionMetadata(
        industry="logistics",
        pain_point="delays",
        goals="improve dispatch",
        data_context="1500 shipments/day",
        stage_reached="EXPLORE",
    )
    snap = update_hypothesis_snapshot(
        meta,
        "We dispatch 1500 shipments per day manually",
        ["We run logistics"],
    )
    stage = promote_funnel_stage(meta, snap)
    assert stage in ("INTEREST", "QUALIFY", "CAPTURE")


def test_conflict_freezes_funnel_promotion() -> None:
    meta = SessionMetadata(stage_reached="INTEREST")
    from app.advisor.types import HypothesisSnapshot

    snap = HypothesisSnapshot(hypothesis_status="conflicted")
    assert promote_funnel_stage(meta, snap) == "INTEREST"
