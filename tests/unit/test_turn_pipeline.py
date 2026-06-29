"""Turn pipeline integration tests."""

from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import ScoredMemoryLine, SessionMetadata


def test_pipeline_detects_logistics_manufacturing_conflict() -> None:
    meta = SessionMetadata(
        active_business_vertical="logistics",
        industry="logistics",
        pain_point="delays",
        goals="improve",
        message_count=3,
        business_memory_lines=[
            ScoredMemoryLine(
                key="business_vertical",
                value="logistics",
                confidence=0.95,
                source_turn=1,
                last_confirmed_turn=1,
            ),
        ],
    )
    history = [
        "We run a logistics company",
        "We dispatch 1500 shipments/day manually. Drivers wait 30-60 minutes.",
    ]
    result = TurnPipeline.run(
        meta,
        "We are a manufacturing company with 40 employees",
        history,
    )
    assert result.snapshot.hypothesis_status == "conflicted"
    assert result.decision_trace.conflict_hold is True
    assert result.extracted_meta.active_business_vertical == "logistics"


def test_pipeline_premature_advice_diagnose_mode() -> None:
    meta = SessionMetadata(industry="logistics", pain_point="delays", goals="scale")
    history = [
        "We dispatch 1500 shipments/day manually. Drivers wait 30-60 minutes.",
    ]
    result = TurnPipeline.run(meta, "What do you recommend?", history)
    assert result.snapshot.overall_confidence >= 0.80
    assert result.router_output.mode == "SALES"


def test_generic_efficiency_no_logistics_question() -> None:
    result = TurnPipeline.run(
        SessionMetadata(),
        "What do you recommend we should do?",
        ["We have operational inefficiencies and want to improve efficiency."],
    )
    q = result.snapshot.required_question or ""
    assert "driver receives which shipment" not in q.lower()
