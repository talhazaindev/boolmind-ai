"""Slim tool output blocks — GROUNDING XOR DELIVERABLE."""

from __future__ import annotations

from app.advisor.constants import RAG_SPARSE_INTERNAL_NOTE
from app.advisor.types import ToolResult

GROUNDING_TOKEN_CAP = 400
DELIVERABLE_TOKEN_CAP = 300


def _approx_tokens(text: str) -> int:
    return len(text) // 4


def _truncate(text: str, cap: int) -> str:
    max_chars = cap * 4
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _chunk_lines(context: str, max_chunks: int = 2) -> list[str]:
    if not context or context == RAG_SPARSE_INTERNAL_NOTE:
        return []
    parts = [p.strip() for p in context.split("\n\n") if p.strip()]
    return parts[:max_chunks]


def build_grounding_block(result: ToolResult | None, tool_name: str) -> tuple[str, str]:
    if result is None or not result.success:
        fallback = result.fallback if result else "unavailable"
        return (
            "unavailable",
            f"GROUNDING: unavailable — {fallback}. Do not invent product features.",
        )
    data = result.data or {}
    context = str(data.get("context", ""))
    if not context or context == RAG_SPARSE_INTERNAL_NOTE or len(_chunk_lines(context)) < 1:
        return (
            "sparse",
            "GROUNDING: sparse — do not invent features; acknowledge limits briefly.",
        )
    chunks = _chunk_lines(context)
    body = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(chunks))
    body = _truncate(body, GROUNDING_TOKEN_CAP)
    return (
        "ok",
        "GROUNDING (authoritative — ground factual claims here only):\n"
        f"{body}\n"
        "Do not claim features absent above.",
    )


def build_deliverable_block(result: ToolResult | None, tool_name: str) -> tuple[str, str]:
    if result is None or not result.success:
        fb = result.fallback if result else "unavailable"
        return ("failed", f"DELIVERABLE: unavailable — {fb}")
    data = result.data or {}
    if tool_name == "product_compare":
        rows = data.get("rows") or []
        text = _truncate(str(rows)[:1200], DELIVERABLE_TOKEN_CAP)
        return ("ok", f"DELIVERABLE (product_compare):\n{text}")
    if tool_name == "generate_architecture_proposal":
        summary = data.get("summary") or data.get("overview") or str(data)[:800]
        text = _truncate(str(summary), DELIVERABLE_TOKEN_CAP)
        return ("ok", f"DELIVERABLE (architecture):\n{text}")
    text = _truncate(str(data)[:800], DELIVERABLE_TOKEN_CAP)
    return ("ok", f"DELIVERABLE ({tool_name}):\n{text}")
