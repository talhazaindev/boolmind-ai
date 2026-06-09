"""Detect when custom-solution complexity is confirmed."""

from __future__ import annotations

_COMPLEXITY_SIGNALS = (
    "payment",
    "payments",
    "scheduling",
    "schedule",
    "enrollment",
    "multi-role",
    "role-based",
    "teacher account",
    "parent portal",
    "integration",
    "booking",
    "subscription",
    "user account",
    "login",
    "sign up",
    "registration",
)


def count_complexity_signals(text: str) -> int:
    lower = text.lower()
    return sum(1 for sig in _COMPLEXITY_SIGNALS if sig in lower)


def is_custom_complexity_confirmed(*texts: str) -> bool:
    """True when 2+ complexity signals appear across provided message texts."""
    total = sum(count_complexity_signals(t) for t in texts if t)
    return total >= 2
