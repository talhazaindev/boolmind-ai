"""Hypothesis snapshot reproducibility."""

from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.types import SessionMetadata


def test_hypothesis_reproducibility() -> None:
    meta = SessionMetadata(industry="logistics", pain_point="delays")
    msg = "We use SAP and manual dispatch for 200+ shipments"
    h = ["prior message"]
    a = update_hypothesis_snapshot(meta, msg, h)
    b = update_hypothesis_snapshot(meta, msg, h)
    assert a.model_dump() == b.model_dump()


def test_required_question_when_unknowns() -> None:
    meta = SessionMetadata()
    snap = update_hypothesis_snapshot(meta, "hello", [])
    assert snap.required_question is not None
