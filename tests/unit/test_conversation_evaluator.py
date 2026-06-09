"""Conversation evaluator tests."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.advisor.orchestrator.conversation_evaluator import (
    _default_evaluation,
    _parse_evaluation,
    evaluate_turn,
)
from app.advisor.types import TurnEvaluation
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.types import PageContext, ReadinessFlags, SessionMetadata


def test_default_evaluation_missing_fields() -> None:
    ev = _default_evaluation(SessionMetadata())
    assert "business_context" in ev.missing_fields
    assert ev.next_discovery_question


def test_parse_evaluation_merges_readiness() -> None:
    raw = json.dumps(
        {
            "stage": "QUALIFY",
            "profile_updates": {
                "industry": "retail",
                "pain_point": "POS fragmentation",
                "goals": "unified reporting",
            },
            "missing_fields": ["data_context"],
            "next_discovery_question": "What systems feed your sales data?",
            "readiness": {
                "architecture": True,
                "product_tour": True,
                "fidp": False,
                "lead_capture": True,
                "booking": False,
            },
            "reasoning": "user described retail pain",
        }
    )
    meta = SessionMetadata(stage_reached="EXPLORE")
    ev = _parse_evaluation(raw, meta)
    assert ev.stage == "QUALIFY"
    assert ev.profile_updates["industry"] == "retail"
    assert ev.next_discovery_question.startswith("What systems")
    assert isinstance(ev.readiness, ReadinessFlags)


@pytest.mark.asyncio
async def test_evaluate_turn_fallback_on_error() -> None:
    with patch(
        "app.advisor.orchestrator.conversation_evaluator.get_groq_rotator"
    ) as mock_rotator:
        mock_rotator.return_value.create_chat_completion = AsyncMock(
            side_effect=RuntimeError("groq down")
        )
        with patch(
            "app.advisor.orchestrator.conversation_evaluator.discovery_evaluated"
        ):
            result = await evaluate_turn(
                session_id="sess-1",
                user_message="We run retail stores",
                history=[],
                profile=SessionMetadata(),
                product_context=ProductContext(
                    active_product=None,
                    active_product_name=None,
                    products_discussed=[],
                    namespace="general",
                ),
                page_context=PageContext(),
            )
    assert isinstance(result, TurnEvaluation)
    assert result.stage == "EXPLORE"


@pytest.mark.asyncio
async def test_evaluate_turn_parses_groq_json() -> None:
    payload = json.dumps(
        {
            "stage": "INTEREST",
            "profile_updates": {"industry": "healthcare"},
            "missing_fields": ["pain_point", "goals"],
            "next_discovery_question": "What clinical workflow are you improving?",
            "readiness": {
                "architecture": False,
                "product_tour": False,
                "fidp": False,
                "lead_capture": False,
                "booking": False,
            },
            "reasoning": "healthcare mention",
        }
    )
    with patch(
        "app.advisor.orchestrator.conversation_evaluator.get_groq_rotator"
    ) as mock_rotator:
        mock_rotator.return_value.create_chat_completion = AsyncMock(return_value=payload)
        with patch(
            "app.advisor.orchestrator.conversation_evaluator.discovery_evaluated"
        ):
            result = await evaluate_turn(
                session_id="sess-2",
                user_message="We are a hospital",
                history=[],
                profile=SessionMetadata(),
                product_context=ProductContext(
                    active_product="ecg",
                    active_product_name="ECG",
                    products_discussed=["ecg"],
                    namespace="ecg",
                ),
                page_context=PageContext(url="https://boolmind.ai/products/ecg"),
            )
    assert result.stage == "INTEREST"
    assert result.profile_updates.get("industry") == "healthcare"
