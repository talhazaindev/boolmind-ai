"""Tool execution with timeouts."""

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
from app.advisor.tools import crm_create_lead, product_compare, product_tour, rag_query
from app.advisor.types import ToolResult

logger = logging.getLogger(__name__)


class TimeoutError(Exception):
    pass


async def with_timeout(coro, ms: int):
    try:
        return await asyncio.wait_for(coro, timeout=ms / 1000.0)
    except asyncio.TimeoutError as e:
        raise TimeoutError(str(e)) from e


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    product_context: ProductContext,
    session_id: str,
    visitor_id: str | None,
) -> ToolResult:
    timeout = TOOL_TIMEOUT_MS.get(name, 3000)
    try:
        if name == "rag_query":
            data = await with_timeout(
                rag_query.handle(arguments, product_context),
                timeout,
            )
            return ToolResult(success=True, data=data)
        if name == "crm_create_lead":
            data = await with_timeout(
                crm_create_lead.handle(arguments, session_id, visitor_id),
                timeout,
            )
            return ToolResult(success=True, data=data)
        if name == "product_tour":
            data = await with_timeout(product_tour.handle(arguments), timeout)
            return ToolResult(success=True, data=data)
        if name == "product_compare":
            data = await with_timeout(product_compare.handle(arguments), timeout)
            return ToolResult(success=True, data=data)
        return ToolResult(success=False, fallback=GENERIC_ERROR_MESSAGE)
    except TimeoutError:
        logger.warning("Tool %s timed out", name)
        if name == "crm_create_lead":
            return ToolResult(success=False, fallback=FALLBACK_CRM_MESSAGE)
        return ToolResult(success=False, fallback=GENERIC_ERROR_MESSAGE)
    except Exception as e:
        logger.exception("Tool %s failed: %s", name, e)
        return ToolResult(success=False, fallback=GENERIC_ERROR_MESSAGE)


def tool_result_content(result: ToolResult) -> str:
    if result.success and result.data is not None:
        return json.dumps(result.data)
    return result.fallback or GENERIC_ERROR_MESSAGE
