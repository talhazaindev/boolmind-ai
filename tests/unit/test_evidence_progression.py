"""Evidence accumulation and question deduplication tests."""

from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.signals.v1 import INFORMATION_GAIN_QUESTIONS
from app.advisor.pipeline.evidence_engine import compute_evidence_score
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import SessionMetadata


def test_evidence_score_progresses_across_logistics_turns() -> None:
    meta = SessionMetadata(message_count=1)
    t1 = update_hypothesis_snapshot(meta, "We run a logistics company", [])
    assert t1.overall_confidence >= 0.24
    assert t1.overall_confidence <= 0.30

    meta2 = meta.model_copy(
        update={
            "industry": "logistics",
            "evidence_score_peak": t1.overall_confidence,
            "message_count": 2,
        }
    )
    history = ["We run a logistics company"]
    msg = (
        "We dispatch around 1,500 shipments per day. Planning is done manually "
        "in spreadsheets by three coordinators. Drivers often wait 30-60 minutes."
    )
    t2 = update_hypothesis_snapshot(meta2, msg, history)
    assert t2.overall_confidence >= 0.80

    meta3 = meta2.model_copy(
        update={"evidence_score_peak": t2.overall_confidence, "message_count": 3}
    )
    t3 = update_hypothesis_snapshot(meta3, "What do you recommend?", history + [msg])
    assert t3.overall_confidence >= 0.80


def test_rich_logistics_context_reaches_hypothesis_validation() -> None:
    meta = SessionMetadata(
        industry="logistics",
        pain_point="delays",
        evidence_score_peak=0.85,
        message_count=3,
    )
    history = [
        "We run a logistics company",
        "We dispatch 1500 shipments/day manually in spreadsheets. "
        "Three coordinators. Drivers wait 30-60 minutes.",
    ]
    snap = update_hypothesis_snapshot(meta, "What do you recommend?", history)
    assert snap.conversation_stage == "HYPOTHESIS_VALIDATION"
    assert snap.primary_bottleneck == "planning"


def test_open_question_not_repeated() -> None:
    meta = SessionMetadata(
        industry="logistics",
        open_question_keys=["routing_constraints"],
        consecutive_question_turns=0,
    )
    history = [
        "We run a logistics company",
        "We dispatch 1500 shipments/day manually. Drivers wait 30-60 minutes.",
    ]
    snap = update_hypothesis_snapshot(meta, "What do you recommend?", history)
    assert snap.required_question is not None
    assert snap.required_question != INFORMATION_GAIN_QUESTIONS["routing_constraints"]


def test_pipeline_suppresses_question_on_architecture() -> None:
    meta = SessionMetadata(
        industry="logistics",
        data_context="1500 shipments/day",
        message_count=5,
        stage_reached="QUALIFY",
    )
    result = TurnPipeline.run(
        meta,
        "Please generate an architecture proposal for our dispatch platform.",
        ["We need a multi-tenant logistics dispatch system with ERP integration."],
    )
    assert result.router_output.mode == "ARCHITECTURE"
    assert result.snapshot.required_question is None
