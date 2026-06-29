"""Intent classification for advisor conversation routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

ARCHITECTURE_SIGNALS = [
    r"\barchitecture\b",
    r"\bdesign\s+(a|the)\s+system\b",
    r"\bintegration\s+pattern\b",
    r"\bpipeline\b",
    r"\bmermaid\b",
    r"\btechnical\s+solution\b",
    r"\bhow\s+would\s+you\s+build\b",
    r"\bdata\s+flow\b",
    r"\bcomponent\s+breakdown\b",
]

CHANNEL_PRIORITIZATION_SIGNALS = [
    r"worth focusing on",
    r"where to invest",
    r"what(?:'s| is) actually worth",
    r"don'?t know what.*worth",
    r"websites?,?\s*seo",
    r"seo,?\s*social",
    r"social media,?\s*online ads",
    r"online ads,?\s*ai",
    r"heard people talk about",
    r"which (?:channel|channels)",
    r"what should i focus on",
]

CONCEPT_SIGNALS = [
    r"what (do you mean|does .+ mean)",
    r"can you explain",
    r"explain what",
    r"not sure what .+ means",
    r"what that actually means",
    r"not sure (?:what|where) .+ (?:mean|start)",
    r"what .+ actually mean",
    r"before i answer.*explain",
]

ADVICE_SIGNALS = [
    r"what would you (do|recommend)",
    r"what should i (do|start)",
    r"in my situation",
    r"if you were (in my|advising)",
    r"what do you recommend",
    r"what would you advise",
    r"help me (figure|decide|understand)",
    r"do i (really )?need",
    r"need a website",
    r"better ways to spend",
    r"would .+ be enough",
    r"what(?:'s| is) actually necessary",
]

ROI_SIGNALS = [
    r"\bworth it\b",
    r"\broi\b",
    r"\breturn on investment\b",
    r"\bjustify\b",
    r"\$\d",
    r"how (do|would) i know",
    r"break[- ]even",
]

OBJECTION_SIGNALS = [
    r"why not (just )?(use )?(wix|squarespace|wordpress|shopify)",
    r"why not (wix|squarespace|wordpress|shopify)",
    r"\bfreelancer\b",
    r"don'?t need custom",
    r"not convinced",
    r"reason not to hire",
    r"biggest reason not",
    r"what makes boolmind different",
    r"vs\.?\s+(wix|squarespace|freelancer)",
]

CONFIDENCE_THRESHOLD = 0.75


@dataclass
class IntentResult:
    intent: str
    confidence: float


def classify_intent(message: str) -> IntentResult:
    lower = message.lower()

    if any(re.search(pat, lower) for pat in CONCEPT_SIGNALS):
        return IntentResult("concept_explanation", 0.9)
    if any(re.search(pat, lower) for pat in CHANNEL_PRIORITIZATION_SIGNALS):
        return IntentResult("channel_prioritization", 0.9)
    if any(re.search(pat, lower) for pat in ADVICE_SIGNALS):
        return IntentResult("advice_request", 0.9)
    if any(re.search(pat, lower) for pat in ROI_SIGNALS):
        return IntentResult("roi_analysis", 0.85)
    if any(re.search(pat, lower) for pat in OBJECTION_SIGNALS):
        return IntentResult("objection", 0.85)

    hits = sum(1 for pat in ARCHITECTURE_SIGNALS if re.search(pat, lower))
    if hits >= 2:
        return IntentResult("technical_solution_request", min(0.5 + hits * 0.15, 0.95))
    if hits == 1:
        return IntentResult("technical_solution_request", 0.6)
    if any(kw in lower for kw in ("compare", " vs ", "difference between")):
        return IntentResult("product_comparison", 0.8)
    if any(kw in lower for kw in ("tour", "walkthrough", "show me how")):
        return IntentResult("product_tour", 0.85)
    if any(kw in lower for kw in ("book", "schedule", "calendar", "demo call")):
        return IntentResult("booking", 0.8)
    return IntentResult("general", 0.5)


def is_solution_architecture_mode(message: str) -> bool:
    result = classify_intent(message)
    return (
        result.intent == "technical_solution_request"
        and result.confidence >= CONFIDENCE_THRESHOLD
    )


def is_advisory_intent(message: str) -> bool:
    result = classify_intent(message)
    return result.intent in ("advice_request", "roi_analysis", "objection")


def is_concept_explanation(message: str) -> bool:
    return classify_intent(message).intent == "concept_explanation"


def is_channel_prioritization(message: str) -> bool:
    return classify_intent(message).intent == "channel_prioritization"


def intent_is_explicit_solution_request(intent: IntentResult) -> bool:
    """User explicitly asked for a solution, recommendation, or architecture."""
    return intent.intent in (
        "advice_request",
        "technical_solution_request",
        "roi_analysis",
    ) and intent.confidence >= CONFIDENCE_THRESHOLD
