"""Turn value delivery — insight and draft visuals per turn."""

from __future__ import annotations

from app.advisor.pipeline.discovery_models import ExtractedFact, FactGraph
from app.advisor.pipeline.turn_value import (
    build_as_is_mermaid,
    build_turn_value,
    detect_draft_confirmation,
    infer_workflow_steps,
    should_deliver_turn_value,
)
from app.advisor.types import SessionMetadata


def _restaurant_graph() -> FactGraph:
    return FactGraph(
        facts=[
            ExtractedFact(
                id="f1",
                category="symptom",
                text="stockouts on weekends",
                normalized="stockouts on weekends",
            ),
            ExtractedFact(
                id="f2",
                category="technology",
                text="paper bills for orders",
                normalized="paper bills for orders",
            ),
        ],
        source_text=(
            "waiters take orders manually on paper bills kitchen coordination "
            "stockouts delivery manual"
        ),
    )


def test_no_value_first_two_turns() -> None:
    meta = SessionMetadata(message_count=2)
    artifact = build_turn_value(_restaurant_graph(), meta)
    assert not artifact.deliver
    assert not should_deliver_turn_value(meta)


def test_value_from_turn_three() -> None:
    meta = SessionMetadata(message_count=3, industry="restaurant")
    artifact = build_turn_value(_restaurant_graph(), meta)
    assert artifact.deliver
    assert artifact.working_summary
    assert artifact.friction_points
    assert artifact.as_is_visual is not None
    assert artifact.as_is_visual.mermaid
    assert "draft" in artifact.prompt_block.lower()


def test_mermaid_from_generic_vocabulary() -> None:
    graph = FactGraph(
        source_text="loan applications per day manual compliance review backlog underwriting"
    )
    steps = infer_workflow_steps(graph)
    mermaid = build_as_is_mermaid(steps)
    assert len(steps) >= 2
    assert "flowchart" in mermaid
    assert "-->" in mermaid


def test_draft_confirmation_detected() -> None:
    assert detect_draft_confirmation("Yes that's right, we can move on")
    assert not detect_draft_confirmation("not sure yet")


def test_confirmed_draft_softens_framing() -> None:
    meta = SessionMetadata(message_count=4, draft_working_picture_confirmed=True)
    artifact = build_turn_value(_restaurant_graph(), meta, draft_confirmed=True)
    assert artifact.deliver
    assert "not a final design" not in artifact.prompt_block.lower()
