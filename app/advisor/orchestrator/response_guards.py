"""Post-generation guards for advisor responses."""

from __future__ import annotations

import re

from app.advisor.orchestrator.diagnostic_validation import (
    response_contains_premature_solutions,
)
from app.advisor.types import ReasoningPhase

_EMAIL_ASK_PATTERNS = [
    r"\b(email|e-mail)\s+(address|id)\b",
    r"\bshare your (name and )?email\b",
    r"\bwhat(?:'s| is) your email\b",
    r"\bcan (you|i) (get|have|share) your (name|email)\b",
]

_PREMATURE_CONTACT_PATTERNS = [
    r"\bshare your name\b",
    r"\bprovide your (name|email)\b",
]


def asks_for_contact(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pat, lower) for pat in _EMAIL_ASK_PATTERNS + _PREMATURE_CONTACT_PATTERNS)


def has_repeated_content(current: str, previous: str) -> bool:
    """Detect duplicate sentences or high prefix overlap with prior assistant turn."""
    if not current.strip() or not previous.strip():
        return False
    cur = current.strip()
    prev = previous.strip()
    if cur[:200] == prev[:200]:
        return True
    cur_sentences = {s.strip().lower() for s in re.split(r"[.!?]\s+", cur) if len(s.strip()) > 30}
    prev_sentences = {s.strip().lower() for s in re.split(r"[.!?]\s+", prev) if len(s.strip()) > 30}
    overlap = cur_sentences & prev_sentences
    if len(overlap) >= 1:
        return True
    # Shared opening clause before first sentence break
    min_len = min(len(cur), len(prev), 80)
    return min_len >= 40 and cur[:min_len] == prev[:min_len]


def email_guard_rewrite_instruction() -> str:
    return (
        "\n\nREWRITE REQUIRED: Remove any request for name or email. "
        "Provide value and a Boolmind next step instead. Do not ask for contact info."
    )


def repetition_rewrite_instruction() -> str:
    return (
        "\n\nREWRITE REQUIRED: Your previous draft repeated earlier content. "
        "Rewrite with fresh phrasing. Do not duplicate sentences from prior turns."
    )


def premature_solution_rewrite_instruction() -> str:
    return (
        "\n\nREWRITE REQUIRED: You proposed solutions before validating the root cause. "
        "Remove all intervention suggestions. State business insight and tradeoff analysis, "
        "then end with ONE comparative validation question only."
    )


_BOOLMIND_MARKERS = ("boolmind", "boolmind.ai")

def response_contains_premature_boolmind(
    text: str,
    reasoning_phase: ReasoningPhase,
) -> bool:
    if reasoning_phase in ("solution_exploration", "boolmind_positioning"):
        return False
    lower = text.lower()
    return any(marker in lower for marker in _BOOLMIND_MARKERS)


def response_missing_hypothesis_structure(
    text: str,
    reasoning_phase: ReasoningPhase,
) -> bool:
    """Phase 2 should enumerate multiple hypotheses."""
    if reasoning_phase != "hypothesis_generation":
        return False
    lower = text.lower()
    if any(kw in lower for kw in ("possibilit", "could be", "hypothes", "several")):
        return False
    hypothesis_terms = (
        "pricing",
        "onboarding",
        "complexity",
        "segment",
        "competition",
        "workload",
        "compensation",
        "retention",
        "conversion",
    )
    hits = sum(1 for term in hypothesis_terms if term in lower)
    return hits < 2


def boolmind_guard_rewrite_instruction() -> str:
    return (
        "\n\nREWRITE REQUIRED: Remove any Boolmind mention. "
        "Stay in diagnostic mode — hypotheses and validation only."
    )


def hypothesis_structure_rewrite_instruction() -> str:
    return (
        "\n\nREWRITE REQUIRED: List 3–5 plausible hypotheses ranked by likelihood, "
        "then end with ONE differentiating question. No solutions yet."
    )
