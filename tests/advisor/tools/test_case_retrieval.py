"""Tests for case evidence retrieval."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.tools import case_retrieval
from app.advisor.tools.case_retrieval import retrieve_case_evidence


def _sample_archetype() -> BusinessArchetype:
    return BusinessArchetype(
        id="lead_leakage",
        name="Lead Leakage",
        symptoms=["leads go cold", "slow follow-up", "no CRM"],
        root_cause="No systematic lead capture",
        it_lever="CRM automation",
        boolmind_services=["CRM customisation"],
        discriminating_question="How quickly do you respond to inbound leads?",
        outcome_frame="Cut response time from hours to minutes for {vertical}",
        case_hook="A consulting firm cut response time from 4 hours to 4 minutes.",
    )


@pytest.mark.asyncio
async def test_retrieve_case_evidence_empty_without_archetypes() -> None:
    result = await retrieve_case_evidence([])
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_case_evidence_returns_empty_on_timeout() -> None:
    arch = _sample_archetype()

    with patch.object(
        case_retrieval.asyncio,
        "wait_for",
        side_effect=asyncio.TimeoutError,
    ):
        result = await retrieve_case_evidence([arch], vertical="consulting")
    assert result == []


@pytest.mark.asyncio
async def test_retrieve_case_evidence_success() -> None:
    arch = _sample_archetype()
    fake_match = SimpleNamespace(
        metadata={
            "case_text": arch.case_hook,
            "outcome_frame": arch.outcome_frame,
            "archetype_name": arch.name,
        }
    )
    fake_result = SimpleNamespace(matches=[fake_match])
    mock_index = MagicMock()
    mock_index.query.return_value = fake_result

    async def _run_sync(fn: object, *args: object, **kwargs: object) -> object:
        assert callable(fn)
        return fn(*args, **kwargs)

    with (
        patch("app.advisor.tools.case_retrieval.embed_query", return_value=[0.1] * 8),
        patch("app.advisor.tools.case_retrieval.get_pinecone_index", return_value=mock_index),
        patch.object(case_retrieval.asyncio, "to_thread", side_effect=_run_sync),
    ):
        result = await retrieve_case_evidence([arch], vertical="consulting", top_k=2)

    assert len(result) == 1
    assert result[0]["case_text"] == arch.case_hook
    assert result[0]["outcome_frame"] == arch.outcome_frame
    assert result[0]["archetype_name"] == arch.name
    mock_index.query.assert_called_once()
    call_kwargs = mock_index.query.call_args.kwargs
    assert call_kwargs["namespace"] == "case_evidence"
    assert call_kwargs["filter"] == {"archetype_id": {"$in": ["lead_leakage"]}}


@pytest.mark.asyncio
async def test_retrieve_case_evidence_returns_empty_on_embed_error() -> None:
    arch = _sample_archetype()

    with patch.object(
        case_retrieval.asyncio,
        "wait_for",
        side_effect=RuntimeError("embed failed"),
    ):
        result = await retrieve_case_evidence([arch])
    assert result == []
