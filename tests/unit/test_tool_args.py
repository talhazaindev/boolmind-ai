"""Tool argument sanitization tests."""

from app.advisor.orchestrator.tool_args import (
    is_groq_validation_error,
    sanitize_tool_arguments,
    strip_groq_validation_errors,
)


def test_sanitize_rag_query_top_k_string() -> None:
    args = sanitize_tool_arguments("rag_query", {"query": "Retify", "top_k": "5"})
    assert args["top_k"] == 5


def test_strip_groq_validation_errors() -> None:
    raw = (
        "I can help with scaling.\n"
        "tool call validation failed: parameters for tool rag_query did not match schema"
    )
    cleaned = strip_groq_validation_errors(raw)
    assert "validation failed" not in cleaned
    assert "I can help" in cleaned


def test_is_groq_validation_error() -> None:
    assert is_groq_validation_error("tool call validation failed: top_k")
