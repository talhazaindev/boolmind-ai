"""Generic business signals and growth framework — no per-industry keyword maps.

Industry-specific tactics belong in the knowledge base (rag_query) and the LLM,
not in hardcoded Python branches for bakeries, fitness studios, accountants, etc.
"""

from __future__ import annotations

import re

from app.advisor.types import SessionMetadata

_MICRO_BUDGET_PATTERNS = (
    r"\$\s*5\s*00\b",
    r"\b500\s*(dollar|usd|budget)\b",
    r"very (tight|small|limited) budget",
    r"almost no budget",
    r"can't afford",
    r"cannot afford",
)

_LOCAL_FOOTPRINT_SIGNALS = (
    "km radius",
    "mile radius",
    "local customers",
    "word of mouth",
    "word-of-mouth",
    "referrals",
    "referral",
    "nearby",
    "live nearby",
    "neighborhood",
    "foot traffic",
    "walk-in",
)

_WEBSITE_PUSHBACK_SIGNALS = (
    "need a website",
    "really need",
    "better ways to spend",
    "marketing budget",
)


def business_label(meta: SessionMetadata) -> str:
    """Human-readable business context from evaluator-extracted fields."""
    return (meta.business_type or meta.industry or "the business").strip()


def _text_blob(meta: SessionMetadata, extra: str = "", history: list[str] | None = None) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        meta.constraints or "",
        extra,
        " ".join(history or []),
    ]
    return " ".join(parts).lower()


def is_local_footprint(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    """True when conversation signals a local / physical customer base (any industry)."""
    return any(sig in _text_blob(meta, message, history) for sig in _LOCAL_FOOTPRINT_SIGNALS)


def is_micro_budget(meta: SessionMetadata, message: str = "") -> bool:
    blob = _text_blob(meta, message)
    return any(re.search(pat, blob) for pat in _MICRO_BUDGET_PATTERNS)


def should_defer_boolmind_pitch(meta: SessionMetadata) -> bool:
    """Hold Boolmind pitch until enough context or stage maturity."""
    if meta.stage_reached in ("QUALIFY", "CAPTURE", "BOOK"):
        return False
    if meta.custom_complexity_confirmed:
        return False
    if meta.message_count >= 5:
        return False
    return True


def generic_phased_framework() -> str:
    """Industry-agnostic growth path — specifics come from rag_query + conversation context."""
    return (
        "Phase 1 — Diagnose: name the growth blocker (discovery, conversion, or retention) "
        "and what's already working.\n"
        "Phase 2 — Channel fit: recommend channels matched to this business model "
        "(ground industry-specific tactics in rag_query, capabilities namespace).\n"
        "Phase 3 — Technology: only when free/low-cost channels are maxed or the user "
        "needs enrollment, booking, payments, or integration beyond manual process."
    )


def rag_industry_guidance_line(meta: SessionMetadata) -> str:
    label = business_label(meta)
    return (
        f"Use rag_query(namespace=capabilities) for growth/marketing tactics suited to "
        f"\"{label}\" — do not rely on generic SEO/Instagram advice without KB grounding."
    )


def micro_budget_advisory() -> str:
    return (
        "MICRO-BUDGET ADVISORY: User has very limited budget. "
        "Honestly recommend they NOT hire Boolmind yet — focus on free/low-cost channels first. "
        "Say when a Boolmind engagement would make sense (e.g. enrollment, booking, payments at scale). "
        "This builds trust; do not pitch a landing page."
    )


def pushback_for_website_question(meta: SessionMetadata, message: str) -> str | None:
    """When user questions a website, push back if local footprint + referrals dominate."""
    lower = message.lower()
    if not any(p in lower for p in _WEBSITE_PUSHBACK_SIGNALS):
        return None
    if is_local_footprint(meta, message) and (
        "referral" in _text_blob(meta, message) or "word of mouth" in _text_blob(meta, message)
    ):
        return (
            "PUSHBACK PERMITTED: Strong local word-of-mouth may mean a website is not the "
            "highest-ROI next step. Diagnose discovery channels first (reviews, local search, "
            "relevant social). Website when they need booking, menus, catalog, or capture beyond walk-ins."
        )
    return None
