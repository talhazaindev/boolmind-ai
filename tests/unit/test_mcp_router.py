"""MCP tool router tests."""

import pytest

from app.advisor.mcp.mcp_tool_router import McpToolRouter, TOOL_SERVER_MAP
from app.advisor.orchestrator.product_context import ProductContext


def test_nine_tools_registered() -> None:
    router = McpToolRouter()
    names = {t["function"]["name"] for t in router.list_tools()}
    assert len(names) == 9
    assert "rag_query" in names
    assert "generate_fidp" in names


def test_tool_server_map() -> None:
    assert TOOL_SERVER_MAP["rag_query"] == "boolmind-knowledge"
    assert TOOL_SERVER_MAP["crm_create_lead"] == "boolmind-crm"


@pytest.mark.asyncio
async def test_rag_query_via_router() -> None:
    from unittest.mock import patch

    router = McpToolRouter()
    ctx = ProductContext(
        active_product="retify",
        active_product_name="Retify",
        products_discussed=[],
        namespace="retify",
    )
    with patch(
        "app.advisor.mcp.mcp_tool_router.rag_query.handle",
        return_value={"context": "10 steps"},
    ):
        result = await router.call_tool(
            "rag_query",
            {"query": "workflow steps"},
            ctx,
            "sess-1",
            None,
        )
    assert result.success
    assert result.data is not None
