"""MCP tool router — dispatches Groq tool calls to server handlers (in-process)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.advisor.constants import (
    FALLBACK_CRM_MESSAGE,
    GENERIC_ERROR_MESSAGE,
    TOOL_TIMEOUT_MS,
)
from app.advisor.integrations.failed_operations import queue_failed_operation
from app.advisor.monitoring.telemetry import emit
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

_FAILED_OPS_TOOLS = frozenset({"crm_create_lead", "calendar_book_slot", "send_meeting_invite"})


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
        server = TOOL_SERVER_MAP.get(name, "unknown")
        product_id = product_context.active_product

        if readiness is not None and not is_tool_allowed(
            name, readiness, product_fit=product_fit
        ):
            logger.info(
                "[advisor.tool] gated tool=%s server=%s session=%s",
                name,
                server,
                session_id,
            )
            await emit(
                "tool_gated",
                session_id,
                visitor_id=visitor_id,
                product_id=product_id,
                metadata={
                    "tool": name,
                    "server": server,
                    "readiness": readiness.model_dump(),
                    "outcome": "gated",
                },
            )
            return ToolResult(
                success=False,
                fallback=gated_tool_fallback(name),
                outcome="gated",
            )

        timeout = TOOL_TIMEOUT_MS.get(name, 3000)
        logger.info(
            "[advisor.tool] invoking tool=%s server=%s session=%s timeout_ms=%d",
            name,
            server,
            session_id,
            timeout,
        )
        await emit(
            "tool_invoked",
            session_id,
            visitor_id=visitor_id,
            product_id=product_id,
            metadata={"tool": name, "server": server, "timeout_ms": timeout},
        )

        start = time.perf_counter()
        try:
            data = await _with_timeout(
                self._dispatch(name, arguments, product_context, session_id, visitor_id),
                timeout,
            )
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.info(
                "[advisor.tool] completed tool=%s server=%s session=%s outcome=success duration_ms=%.1f",
                name,
                server,
                session_id,
                duration_ms,
            )
            await emit(
                "tool_completed",
                session_id,
                visitor_id=visitor_id,
                product_id=product_id,
                metadata={
                    "tool": name,
                    "server": server,
                    "duration_ms": duration_ms,
                    "outcome": "success",
                },
            )
            return ToolResult(
                success=True,
                data=data,
                duration_ms=duration_ms,
                outcome="success",
            )
        except TimeoutError:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.warning(
                "[advisor.tool] timeout tool=%s server=%s session=%s duration_ms=%.1f timeout_ms=%d",
                name,
                server,
                session_id,
                duration_ms,
                timeout,
            )
            await emit(
                "tool_timeout",
                session_id,
                visitor_id=visitor_id,
                product_id=product_id,
                metadata={
                    "tool": name,
                    "server": server,
                    "duration_ms": duration_ms,
                    "timeout_ms": timeout,
                    "outcome": "timeout",
                },
            )
            if name in _FAILED_OPS_TOOLS:
                await queue_failed_operation(
                    name,
                    arguments,
                    f"timeout after {timeout}ms",
                    session_id=session_id,
                )
            if name == "crm_create_lead":
                return ToolResult(
                    success=False,
                    fallback=FALLBACK_CRM_MESSAGE,
                    duration_ms=duration_ms,
                    outcome="timeout",
                )
            return ToolResult(
                success=False,
                fallback=GENERIC_ERROR_MESSAGE,
                duration_ms=duration_ms,
                outcome="timeout",
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.exception(
                "[advisor.tool] failed tool=%s server=%s session=%s duration_ms=%.1f",
                name,
                server,
                session_id,
                duration_ms,
            )
            await emit(
                "tool_failed",
                session_id,
                visitor_id=visitor_id,
                product_id=product_id,
                metadata={
                    "tool": name,
                    "server": server,
                    "duration_ms": duration_ms,
                    "error_class": type(e).__name__,
                    "outcome": "error",
                },
                exception=e,
            )
            if name in _FAILED_OPS_TOOLS:
                await queue_failed_operation(
                    name,
                    arguments,
                    str(e)[:500],
                    session_id=session_id,
                )
            return ToolResult(
                success=False,
                fallback=GENERIC_ERROR_MESSAGE,
                duration_ms=duration_ms,
                outcome="error",
            )

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
