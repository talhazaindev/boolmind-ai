"""Shared validation gate — evidence ≠ confirmed root cause.

Consulting flow: Problem → Evidence → Hypothesis → Validation → Insight → Solution.
All dimension-specific diagnosis modules use these helpers.
"""

from __future__ import annotations

import re

_UNSURE_SIGNALS = (
    "not sure",
    "unsure",
    "don't know if",
    "dont know if",
    "don't know whether",
    "dont know whether",
    "whether",
    "or something else",
    "trying to figure out",
    "figure out whether",
    "what do you think",
)

_EVIDENCE_WITHOUT_CONFIRMATION = (
    "most common feedback",
    "common feedback",
    "primary concern",
    "primary concerns",
    "comes up occasionally",
    "not as often",
    "some say",
    "some complain",
    "teachers feel",
    "employees feel",
    "staff say",
    "feedback is that",
    "feedback suggests",
)

_CONFIRMATION_SIGNALS = (
    "the main reason is",
    "the primary reason is",
    "the biggest reason is",
    "it's definitely",
    "it is definitely",
    "confirmed that",
    "mostly because",
    "primarily because",
    "number one reason",
    "the root cause is",
)

_SOLUTION_PREMATURE_PATTERNS = (
    "have you considered",
    "you could try",
    "you might want to implement",
    "i recommend implementing",
    "such as staffing",
    "professional development programs",
    "mentorship opportunities",
    "project management tools",
)


def user_expressed_uncertainty(message: str, history: list[str] | None = None) -> bool:
    blob = " ".join((history or []) + [message]).lower()
    return any(sig in blob for sig in _UNSURE_SIGNALS)


def user_provided_evidence_without_confirmation(
    message: str,
    history: list[str] | None = None,
) -> bool:
    """User shared feedback/signals but did not confirm a single dominant cause."""
    blob = " ".join((history or []) + [message]).lower()
    return any(sig in blob for sig in _EVIDENCE_WITHOUT_CONFIRMATION)


def user_confirmed_dominant_cause(message: str, history: list[str] | None = None) -> bool:
    blob = " ".join((history or []) + [message]).lower()
    if any(sig in blob for sig in _CONFIRMATION_SIGNALS):
        return True
    return bool(re.search(r"the (main|primary|biggest) (issue|reason|cause|driver) is", blob))


def hypotheses_need_validation(
    hypotheses: list[str],
    message: str,
    history: list[str] | None,
    confirmed: str | None = None,
    *,
    force_when_empty_keywords: tuple[str, ...] = (),
) -> bool:
    """True while root cause is not validated — stay in diagnose mode."""
    if confirmed and confirmed not in ("unknown", "multiple"):
        return False

    if user_expressed_uncertainty(message, history):
        return True

    if len(hypotheses) > 1:
        return True

    if user_provided_evidence_without_confirmation(message, history):
        if user_confirmed_dominant_cause(message, history) and len(hypotheses) == 1:
            return False
        return True

    if len(hypotheses) == 0:
        blob = " ".join((history or []) + [message]).lower()
        return any(kw in blob for kw in force_when_empty_keywords)

    return False


def no_solutions_clause() -> str:
    return (
        "Do NOT recommend interventions, programs, tools, hiring, or software this turn. "
        "Do NOT ask \"have you considered…\" — that presumes the root cause. "
        "Do NOT list solution options (mentorship, training, staffing, PM tools, etc.)."
    )


def premature_solution_rewrite_instruction() -> str:
    return (
        "\n\nREWRITE REQUIRED: You proposed solutions before validating the root cause. "
        "Remove all intervention suggestions. State business insight and tradeoff analysis, "
        "then end with ONE comparative validation question only."
    )


def response_contains_premature_solutions(text: str) -> bool:
    lower = text.lower()
    return any(pat in lower for pat in _SOLUTION_PREMATURE_PATTERNS)
