"""Golden-path fixture tests for turn pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import SessionMetadata

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "golden"


@pytest.mark.parametrize(
    "fixture_path",
    sorted(FIXTURES.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_golden_pipeline_fixture(fixture_path: Path) -> None:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    meta = SessionMetadata.model_validate(data["frozen_meta"])
    result = TurnPipeline.run(meta, data["message"], data.get("history", []))
    expect = data["expect"]

    if expect.get("conflict_hold"):
        assert result.decision_trace.conflict_hold is True
        assert result.snapshot.hypothesis_status == "conflicted"

    if "execution_mode" in expect:
        assert result.router_output.mode == expect["execution_mode"]

    if "execution_mode_not" in expect:
        assert result.router_output.mode != expect["execution_mode_not"]

    if "vertical_unchanged" in expect:
        assert result.extracted_meta.active_business_vertical == expect["vertical_unchanged"]
