"""Integration tests for discovery profile persistence."""

import pytest

from app.advisor.orchestrator.session_metadata import (
    merge_profile_updates,
    persist_discovery_evaluation,
)
from app.advisor.types import ReadinessFlags, SessionMetadata


class _MemoryRedis:
    def __init__(self) -> None:
        self.store: dict[str, SessionMetadata] = {}

    async def save_visitor_metadata(self, visitor_id: str, meta: SessionMetadata) -> None:
        self.store[visitor_id] = meta

    async def get_visitor_metadata(self, visitor_id: str) -> SessionMetadata | None:
        return self.store.get(visitor_id)


@pytest.mark.asyncio
async def test_persist_discovery_updates_stage() -> None:
    redis = _MemoryRedis()
    existing = SessionMetadata(stage_reached="EXPLORE")
    meta = await persist_discovery_evaluation(
        redis,  # type: ignore[arg-type]
        "visitor-1",
        existing,
        stage="QUALIFY",
        profile_updates={
            "industry": "retail",
            "pain_point": "siloed POS",
            "goals": "unified dashboard",
        },
        missing_fields=["data_context"],
        llm_readiness=ReadinessFlags(lead_capture=True),
    )
    assert meta.stage_reached == "QUALIFY"
    assert meta.industry == "retail"
    assert meta.missing_fields == ["data_context"]
    saved = await redis.get_visitor_metadata("visitor-1")
    assert saved is not None
    assert saved.stage_reached == "QUALIFY"


def test_merge_profile_updates_skips_empty_strings() -> None:
    meta = SessionMetadata(industry="legal")
    merged = merge_profile_updates(meta, {"industry": "", "pain_point": "contracts"})
    assert merged.industry == "legal"
    assert merged.pain_point == "contracts"


def test_merge_profile_remaps_float_qualification_to_confidence() -> None:
    """LLM often sends 0.7 as qualification_score instead of product_fit_confidence."""
    meta = SessionMetadata()
    merged = merge_profile_updates(meta, {"qualification_score": 0.7})
    assert merged.qualification_score is None
    assert merged.product_fit_confidence == 0.7


def test_merge_profile_coerces_integer_qualification_score() -> None:
    meta = SessionMetadata()
    merged = merge_profile_updates(meta, {"qualification_score": 8})
    assert merged.qualification_score == 8
    assert merged.product_fit_confidence == 0.0


def test_merge_profile_persists_reasoning_fields() -> None:
    meta = SessionMetadata()
    merged = merge_profile_updates(
        meta,
        {
            "business_model": "saas",
            "reasoning_phase": "hypothesis_testing",
            "funnel_stage": "conversion",
        },
    )
    assert merged.business_model == "saas"
    assert merged.reasoning_phase == "hypothesis_testing"
    assert merged.funnel_stage == "conversion"
