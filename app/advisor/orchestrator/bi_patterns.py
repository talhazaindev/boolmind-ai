"""Deterministic BI pattern snippets for question composer (offline fallback)."""

from __future__ import annotations

_BI_SNIPPETS: dict[str, list[str]] = {
    "throughput:quality_gate": [
        "Is the delay mostly queue volume waiting for review, or rework caused by "
        "exceptions that automation missed?",
    ],
    "throughput:exception_loop": [
        "When exceptions hit, do they bounce back to the same team or get routed "
        "to specialists — and how is that decided?",
    ],
    "throughput:preparation": [
        "Is the preparation bottleneck more about gathering information, verifying it, "
        "or re-entering it into your system?",
    ],
    "growth:unknown": [
        "Where in the customer journey does momentum stall most — discovery, first "
        "purchase, or repeat business?",
    ],
}


def bi_pattern_snippets(
    problem_dimension: str | None,
    universal_stage: str | None,
) -> list[str]:
    dim = problem_dimension or "throughput"
    stage = universal_stage or "unknown"
    key = f"{dim}:{stage}"
    if key in _BI_SNIPPETS:
        return list(_BI_SNIPPETS[key])
    return list(_BI_SNIPPETS.get(f"{dim}:unknown", _BI_SNIPPETS.get("throughput:quality_gate", [])))
