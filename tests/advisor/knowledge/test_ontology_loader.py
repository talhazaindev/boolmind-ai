"""Tests for business problem ontology loader and pipeline integration."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.advisor.knowledge.ontology_loader import (
    _ensure_cache,
    _load_archetypes,
    match_archetypes_sync,
)
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import SessionMetadata


def _fake_embed(text: str) -> list[float]:
    """Deterministic fake embedding keyed on text hash."""
    seed = sum(ord(c) for c in text) % 1000
    return [float((seed + i) % 97) / 97.0 for i in range(8)]


def test_load_archetypes_count() -> None:
    archetypes = _load_archetypes()
    assert len(archetypes) == 25


def test_load_archetypes_fields() -> None:
    for arch in _load_archetypes():
        assert arch.discriminating_question.strip()
        assert "tell me more" not in arch.discriminating_question.lower()
        assert len(arch.symptoms) >= 1
        assert len(arch.boolmind_services) >= 1
        assert arch.id
        assert arch.name


@patch("app.advisor.knowledge.ontology_loader.embed_query", side_effect=RuntimeError("embed down"))
def test_match_returns_empty_on_embed_failure(_mock_embed: object) -> None:
    import app.advisor.knowledge.ontology_loader as loader_mod

    loader_mod._cache_loaded = False
    loader_mod._archetypes = []
    loader_mod._archetype_embeddings = []

    result = match_archetypes_sync(
        current_message="we lose track of leads",
        recent_user_turns=[],
    )
    assert result == []


@patch("app.advisor.knowledge.ontology_loader.embed_query", side_effect=_fake_embed)
def test_ensure_cache_idempotent(mock_embed: object) -> None:
    import app.advisor.knowledge.ontology_loader as loader_mod

    loader_mod._cache_loaded = False
    loader_mod._archetypes = []
    loader_mod._archetype_embeddings = []

    asyncio.run(_ensure_cache())
    first_call_count = mock_embed.call_count  # type: ignore[attr-defined]

    asyncio.run(_ensure_cache())
    second_call_count = mock_embed.call_count  # type: ignore[attr-defined]

    assert first_call_count == 25
    assert second_call_count == first_call_count


@patch("app.advisor.knowledge.ontology_loader.embed_query", side_effect=_fake_embed)
def test_turn_pipeline_does_not_break(_mock_embed: object) -> None:
    import app.advisor.knowledge.ontology_loader as loader_mod

    loader_mod._cache_loaded = False
    loader_mod._archetypes = []
    loader_mod._archetype_embeddings = []

    result = TurnPipeline.run(
        SessionMetadata(),
        "We lose track of leads and follow-ups fall through the cracks",
        [],
    )
    assert result.extracted_meta is not None
    assert result.snapshot is not None
    bss_state = result.extracted_meta.business_systems_state
    assert "business_context" in bss_state
