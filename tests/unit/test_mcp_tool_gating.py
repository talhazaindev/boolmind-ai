"""MCP router readiness gate tests."""

import pytest

from app.advisor.mcp.mcp_tool_router import McpToolRouter
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.types import ReadinessFlags


@pytest.mark.asyncio
async def test_router_blocks_gated_tool_when_not_ready() -> None:
    router = McpToolRouter()
    readiness = ReadinessFlags()
    result = await router.call_tool(
        "product_tour",
        {"product_id": "retify"},
        ProductContext(
            active_product="retify",
            active_product_name="Retify",
            products_discussed=["retify"],
            namespace="retify",
        ),
        "sess-1",
        None,
        readiness=readiness,
    )
    assert result.success is False
    assert result.fallback is not None
