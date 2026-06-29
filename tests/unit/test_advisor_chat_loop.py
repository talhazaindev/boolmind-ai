"""Advisor chat loop — api_messages must include tool results between rounds."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.advisor.orchestrator.loop import AdvisorChatLoop
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.types import PageContext, ReadinessFlags, SessionMetadata, TurnEvaluation


class _FakeDelta:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[Any] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChoice:
    def __init__(self, delta: _FakeDelta) -> None:
        self.delta = delta


class _FakeChunk:
    def __init__(self, delta: _FakeDelta) -> None:
        self.choices = [_FakeChoice(delta)]


class _FakeToolCall:
    def __init__(self, index: int, name: str, arguments: str, call_id: str) -> None:
        self.index = index
        self.id = call_id
        self.function = MagicMock(name=name, arguments=arguments)


@pytest.mark.asyncio
async def test_groq_receives_tool_messages_on_second_round() -> None:
    """After a tool round, the next Groq call must include assistant + tool messages."""
    messages_seen: list[list[dict[str, Any]]] = []
    call_count = 0

    async def fake_create_chat_stream(
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = "auto",
    ) -> Any:
        nonlocal call_count
        call_count += 1
        messages_seen.append(list(messages))

        async def _gen():
            if call_count == 1:
                yield _FakeChunk(
                    _FakeDelta(
                        tool_calls=[
                            _FakeToolCall(
                                0,
                                "rag_query",
                                json.dumps({"query": "Retify", "namespace": "retify"}),
                                "call_1",
                            )
                        ]
                    )
                )
            else:
                yield _FakeChunk(_FakeDelta(content="Retify unifies retail data."))

        return _gen()

    redis = AsyncMock()
    redis.get_history.return_value = []
    redis.append_history = AsyncMock()

    router = MagicMock()
    router.list_tools.return_value = []
    router.call_tool = AsyncMock(
        return_value=MagicMock(success=True, data={"context": "kb"}, fallback=None)
    )
    router.result_content.return_value = '{"context": "kb"}'

    groq = MagicMock()
    groq.create_chat_stream = fake_create_chat_stream

    loop = AdvisorChatLoop(redis)
    loop._groq = groq

    events: list[dict[str, Any]] = []
    default_eval = TurnEvaluation(
        stage="EXPLORE",
        missing_fields=["business_context"],
        next_discovery_question="What industry are you in?",
        readiness=ReadinessFlags(),
    )
    with patch("app.advisor.orchestrator.loop.get_tool_router", return_value=router), patch(
        "app.advisor.orchestrator.loop.get_mcp_host"
    ), patch("app.advisor.orchestrator.loop.message_sent"), patch(
        "app.advisor.orchestrator.loop.product_discussed"
    ), patch(
        "app.advisor.orchestrator.loop.evaluate_turn", new_callable=AsyncMock, return_value=default_eval
    ), patch(
        "app.advisor.orchestrator.loop.persist_discovery_evaluation",
        new_callable=AsyncMock,
        return_value=SessionMetadata(stage_reached="EXPLORE"),
    ), patch(
        "app.advisor.orchestrator.loop.persist_visitor_metadata", new_callable=AsyncMock
    ):
        async for evt in loop.stream_chat(
            session_id="sess-1",
            message="What is Retify?",
            page_context=PageContext(),
            visitor_id=None,
            user_language="en",
            product_context=ProductContext(
                active_product="retify",
                active_product_name="Retify",
                products_discussed=[],
                namespace="retify",
            ),
            session_meta=None,
        ):
            events.append(evt)

    assert call_count >= 2
    second_payload = messages_seen[1]
    roles = [m["role"] for m in second_payload if m["role"] != "system"]
    assert "assistant" in roles
    assert "tool" in roles
    deltas = [e for e in events if e.get("type") == "delta"]
    assert deltas
    assert "".join(d["content"] for d in deltas) == "Retify unifies retail data."
