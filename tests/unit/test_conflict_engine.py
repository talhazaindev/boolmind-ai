"""Conflict engine tests."""

from app.advisor.pipeline.conflict_engine import detect_conflicts
from app.advisor.pipeline.fact_extractor import extract_message_facts
from app.advisor.types import ScoredMemoryLine, SessionMetadata


def test_vertical_switch_on_frozen_meta() -> None:
    frozen = SessionMetadata(active_business_vertical="logistics", industry="logistics")
    memory = [
        ScoredMemoryLine(
            key="business_vertical",
            value="logistics",
            confidence=0.95,
            source_turn=1,
            last_confirmed_turn=1,
        ),
    ]
    facts = extract_message_facts(
        "We are a manufacturing company with 40 employees", []
    )
    report = detect_conflicts(
        frozen,
        memory,
        facts,
        "We are a manufacturing company with 40 employees",
    )
    assert report.is_conflicted is True
    assert report.blocks_vertical_update is True
    assert report.clarification_question is not None
    assert "logistics" in report.clarification_question.lower()
    assert "manufacturing" in report.clarification_question.lower()


def test_no_conflict_when_vertical_unchanged() -> None:
    frozen = SessionMetadata(active_business_vertical="logistics")
    facts = extract_message_facts("We dispatch 500 shipments per day", [])
    report = detect_conflicts(frozen, [], facts, "We dispatch 500 shipments per day")
    assert report.is_conflicted is False


def test_scale_mismatch_conflict() -> None:
    frozen = SessionMetadata()
    memory = [
        ScoredMemoryLine(
            key="employee_count",
            value="50",
            confidence=0.9,
            source_turn=1,
            last_confirmed_turn=1,
        ),
    ]
    facts = extract_message_facts("We now have 500 employees", [])
    report = detect_conflicts(frozen, memory, facts, "We now have 500 employees")
    assert report.is_conflicted is True
    assert any(r.kind == "scale_mismatch" for r in report.records)
