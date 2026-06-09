"""Post-generation guards for advisor responses."""

from __future__ import annotations

import re

from app.advisor.orchestrator.diagnostic_validation import (
    response_contains_premature_solutions,
)

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
