"""RAG timeout and namespace narrowing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.advisor.constants import RAG_SOFT_TIMEOUT_MS, TOOL_TIMEOUT_MS
from app.advisor.orchestrator.rag_query_builder import resolve_namespace
from app.advisor.types import ProductFitDecision, ToolResult

T = TypeVar("T")


async def call_with_rag_degradation(
    tool_name: str,
    call_fn: Callable[[], Awaitable[ToolResult]],
) -> tuple[ToolResult, str]:
    """Run tool with hard timeout; return (result, rag_status)."""
    hard_ms = TOOL_TIMEOUT_MS.get(tool_name, 3000)
    try:
        result = await asyncio.wait_for(call_fn(), timeout=hard_ms / 1000.0)
        if result.success:
            return result, "ok"
        if result.outcome == "timeout":
            return result, "timeout"
        if result.outcome == "gated":
            return result, "skipped"
        return result, "failed"
    except TimeoutError:
        return (
            ToolResult(
                success=False,
                fallback="Retrieval timed out — proceed without grounding.",
                outcome="timeout",
            ),
            "timeout",
        )
    except Exception:
        return (
            ToolResult(
                success=False,
                fallback="Retrieval failed — proceed without grounding.",
                outcome="error",
            ),
            "failed",
        )


def narrow_rag_namespace(
    namespace: str,
    fit: ProductFitDecision,
    active_product: str | None,
) -> str:
    return resolve_namespace(namespace, fit, active_product)
