"""MCP tool router — dispatches Groq tool calls to server handlers (in-process)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.advisor.constants import (
    FALLBACK_CRM_MESSAGE,
    GENERIC_ERROR_MESSAGE,
    TOOL_TIMEOUT_MS,
)
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.orchestrator.tools import get_tool_definitions
from app.advisor.tools import (
    calendar_book_slot,
    calendar_get_slots,
    crm_create_lead,
    generate_architecture_proposal,
    generate_fidp,
    product_compare,
    product_tour,
    rag_query,
    send_meeting_invite,
)
from app.advisor.tools.handlers import TimeoutError, tool_result_content
from app.advisor.orchestrator.tool_gating import gated_tool_fallback, is_tool_allowed
from app.advisor.types import ReadinessFlags, ToolResult

logger = logging.getLogger(__name__)

# Tool name -> server id (spec decomposition)
TOOL_SERVER_MAP: dict[str, str] = {
    "rag_query": "boolmind-knowledge",
    "product_compare": "boolmind-knowledge",
    "crm_create_lead": "boolmind-crm",
    "calendar_get_slots": "boolmind-calendar",
    "calendar_book_slot": "boolmind-calendar",
    "send_meeting_invite": "boolmind-calendar",
    "product_tour": "boolmind-experience",
    "generate_architecture_proposal": "boolmind-experience",
    "generate_fidp": "boolmind-experience",
}


async def _with_timeout(coro, ms: int):
    try:
        return await asyncio.wait_for(coro, timeout=ms / 1000.0)
    except asyncio.TimeoutError as e:
        raise TimeoutError(str(e)) from e


class McpToolRouter:
    """Routes tool execution to MCP server handler libraries."""

    def list_tools(self) -> list[dict[str, Any]]:
        return get_tool_definitions()

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        product_context: ProductContext,
        session_id: str,
        visitor_id: str | None,
        readiness: ReadinessFlags | None = None,
        product_fit: str | None = None,
    ) -> ToolResult:
        if readiness is not None and not is_tool_allowed(
            name, readiness, product_fit=product_fit
        ):
            logger.info("MCP tool %s blocked by readiness gate", name)
            return ToolResult(success=False, fallback=gated_tool_fallback(name))

        timeout = TOOL_TIMEOUT_MS.get(name, 3000)
        server = TOOL_SERVER_MAP.get(name, "unknown")
        try:
            data = await _with_timeout(
                self._dispatch(name, arguments, product_context, session_id, visitor_id),
                timeout,
            )
            logger.debug("MCP tool %s via %s ok", name, server)
            return ToolResult(success=True, data=data)
        except TimeoutError:
            logger.warning("MCP tool %s timed out (%s)", name, server)
            if name == "crm_create_lead":
                return ToolResult(success=False, fallback=FALLBACK_CRM_MESSAGE)
            return ToolResult(success=False, fallback=GENERIC_ERROR_MESSAGE)
        except Exception as e:
            logger.exception("MCP tool %s failed: %s", name, e)
            return ToolResult(success=False, fallback=GENERIC_ERROR_MESSAGE)

    async def _dispatch(
        self,
        name: str,
        arguments: dict[str, Any],
        product_context: ProductContext,
        session_id: str,
        visitor_id: str | None,
    ) -> dict[str, Any]:
        if name == "rag_query":
            return await rag_query.handle(arguments, product_context)
        if name == "product_compare":
            return await product_compare.handle(arguments)
        if name == "crm_create_lead":
            return await crm_create_lead.handle(arguments, session_id, visitor_id)
        if name == "product_tour":
            return await product_tour.handle(arguments)
        if name == "calendar_get_slots":
            return await calendar_get_slots.handle(arguments)
        if name == "calendar_book_slot":
            return await calendar_book_slot.handle(arguments)
        if name == "send_meeting_invite":
            return await send_meeting_invite.handle(arguments)
        if name == "generate_architecture_proposal":
            return await generate_architecture_proposal.handle(arguments)
        if name == "generate_fidp":
            return await generate_fidp.handle(arguments)
        raise ValueError(f"Unknown tool: {name}")

    @staticmethod
    def result_content(result: ToolResult) -> str:
        return tool_result_content(result)


_router: McpToolRouter | None = None


def get_tool_router() -> McpToolRouter:
    global _router
    if _router is None:
        _router = McpToolRouter()
    return _router
