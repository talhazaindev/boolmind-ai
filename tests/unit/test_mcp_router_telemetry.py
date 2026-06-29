"""MCP router telemetry tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.advisor.integrations.failed_operations import clear_memory_queue, get_memory_queue
from app.advisor.mcp.mcp_tool_router import McpToolRouter
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.types import ReadinessFlags


@pytest.fixture(autouse=True)
def _clear_failed_ops() -> None:
    clear_memory_queue()
    yield
    clear_memory_queue()


@pytest.mark.asyncio
async def test_gated_tool_emits_and_returns_outcome() -> None:
    router = McpToolRouter()
    ctx = ProductContext(
        active_product="retify",
        active_product_name="Retify",
        products_discussed=[],
        namespace="retify",
    )
    readiness = ReadinessFlags()
    with patch("app.advisor.mcp.mcp_tool_router.emit", new_callable=AsyncMock) as mock_emit:
        result = await router.call_tool(
            "crm_create_lead",
            {"email": "a@b.com", "name": "Test"},
            ctx,
            "sess-gate",
            None,
            readiness=readiness,
        )
    assert result.success is False
    assert result.outcome == "gated"
    event_types = [c.args[0] for c in mock_emit.call_args_list]
    assert "tool_gated" in event_types


@pytest.mark.asyncio
async def test_crm_timeout_queues_failed_op() -> None:
    router = McpToolRouter()
    ctx = ProductContext(
        active_product="retify",
        active_product_name="Retify",
        products_discussed=[],
        namespace="retify",
    )

    async def slow(*_a, **_k):
        await asyncio.sleep(5)
        return {"status": "created"}

    with patch("app.advisor.mcp.mcp_tool_router.crm_create_lead.handle", side_effect=slow):
        with patch("app.advisor.mcp.mcp_tool_router.TOOL_TIMEOUT_MS", {"crm_create_lead": 50}):
            with patch("app.advisor.mcp.mcp_tool_router.emit", new_callable=AsyncMock):
                result = await router.call_tool(
                    "crm_create_lead",
                    {"email": "a@b.com", "name": "Test"},
                    ctx,
                    "sess-timeout",
                    None,
                )
    assert result.success is False
    assert result.outcome == "timeout"
    queue = get_memory_queue()
    assert len(queue) == 1
    assert queue[0]["operation"] == "crm_create_lead"


@pytest.mark.asyncio
async def test_success_includes_duration() -> None:
    router = McpToolRouter()
    ctx = ProductContext(
        active_product="retify",
        active_product_name="Retify",
        products_discussed=[],
        namespace="retify",
    )
    with patch(
        "app.advisor.mcp.mcp_tool_router.rag_query.handle",
        return_value={"context": "ok"},
    ):
        with patch("app.advisor.mcp.mcp_tool_router.emit", new_callable=AsyncMock):
            result = await router.call_tool(
                "rag_query",
                {"query": "steps"},
                ctx,
                "sess-ok",
                None,
            )
    assert result.success is True
    assert result.outcome == "success"
    assert result.duration_ms is not None
    assert result.duration_ms >= 0
