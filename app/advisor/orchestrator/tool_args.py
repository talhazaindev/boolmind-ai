"""Coerce LLM tool arguments to schema types (Groq strict validation)."""

from __future__ import annotations

from typing import Any

_GROQ_VALIDATION_SNIPPET = "tool call validation failed"


def is_groq_validation_error(text: str) -> bool:
    return _GROQ_VALIDATION_SNIPPET in text.lower()


def strip_groq_validation_errors(text: str) -> str:
    """Remove Groq tool-validation error lines from assistant text."""
    if not text:
        return text
    lines = [ln for ln in text.splitlines() if not is_groq_validation_error(ln)]
    return "\n".join(lines).strip()


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sanitize_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Normalize types before tool execution (LLMs often emit numeric fields as strings)."""
    args = dict(arguments)
    if tool_name == "rag_query":
        if "top_k" in args:
            args["top_k"] = _coerce_int(args.get("top_k"), 3)
    elif tool_name == "product_tour":
        if "start_step" in args:
            args["start_step"] = _coerce_int(args.get("start_step"), 1)
    elif tool_name == "crm_create_lead":
        if "qualification_score" in args:
            args["qualification_score"] = _coerce_int(args.get("qualification_score"), 5)
    return args
